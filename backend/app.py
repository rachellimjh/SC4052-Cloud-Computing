"""FastAPI application — REST + WebSocket endpoints for VibeCoder.

Endpoints:
  POST   /api/sessions              Create a new session
  GET    /api/sessions              List all sessions
  GET    /api/sessions/{id}/files   List files in session workspace
  GET    /api/sessions/{id}/files/{path}  Read a file from the workspace
  POST   /api/sessions/{id}/chat    Send a message (non-streaming)
  WS     /api/sessions/{id}/ws      WebSocket for streaming agent events
"""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.agent.loop import AgentLoop, TEACHING_SYSTEM_PROMPT
from backend.agent.providers.base import Provider
from backend.agent.providers.claude import ClaudeProvider
from backend.agent.providers.gemini import GeminiProvider
from backend.agent.tools.read_file import ReadFileTool
from backend.agent.tools.write_file import WriteFileTool
from backend.agent.tools.list_files import ListFilesTool
from backend.agent.tools.run_code import RunCodeTool
from backend.sessions.manager import SessionManager, DisplayMessage

load_dotenv()

app = FastAPI(title="c0der", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global state ---

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACES_DIR = BASE_DIR / "workspaces"
sessions = SessionManager(WORKSPACES_DIR)


def _get_provider() -> Provider:
    """Auto-detect which LLM provider to use based on environment variables."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    if gemini_key:
        return GeminiProvider(api_key=gemini_key)
    elif anthropic_key:
        return ClaudeProvider(api_key=anthropic_key)
    else:
        raise HTTPException(
            500,
            "No API key set. Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env",
        )


def _build_agent(workspace: Path, on_event=None, teaching_mode: bool = False) -> AgentLoop:
    """Construct an agent with all tools bound to the given workspace."""
    provider = _get_provider()
    tools = [
        ReadFileTool(workspace),
        WriteFileTool(workspace),
        ListFilesTool(workspace),
        RunCodeTool(workspace),
    ]
    system_prompt = TEACHING_SYSTEM_PROMPT if teaching_mode else None
    return AgentLoop(provider=provider, tools=tools, on_event=on_event, system_prompt=system_prompt)


# --- Pydantic models ---

class ChatRequest(BaseModel):
    message: str
    teaching_mode: bool = False


class RunRequest(BaseModel):
    path: str
    content: str


# --- Session endpoints ---

@app.post("/api/sessions")
def create_session():
    session = sessions.create()
    return {"id": session.id, "title": session.title}


@app.get("/api/sessions")
def list_sessions():
    return sessions.list_all()


@app.get("/api/sessions/{session_id}/files")
def list_files(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return sessions.get_files(session_id)


@app.get("/api/sessions/{session_id}/files/{file_path:path}")
def read_file(session_id: str, file_path: str):
    content = sessions.read_file(session_id, file_path)
    if content is None:
        raise HTTPException(404, "File not found")
    return {"path": file_path, "content": content}


# --- Chat history endpoints ---

@app.delete("/api/sessions/{session_id}/history")
def clear_history(session_id: str):
    """Clear a session's conversation history (workspace files are preserved)."""
    if not sessions.clear_history(session_id):
        raise HTTPException(404, "Session not found")
    return {"ok": True}


@app.get("/api/sessions/{session_id}/history")
def get_history(session_id: str):
    """Return display messages for a session (for restoring chat on switch)."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return [
        {
            "kind": m.kind,
            "content": m.content,
            "tool": m.tool,
            "params": m.params,
            "result": m.result,
        }
        for m in session.display
    ]


# --- Chat endpoint (non-streaming) ---

@app.post("/api/sessions/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Update session title from first message
    if not session.history:
        session.title = req.message[:50]

    # Save user message to display history
    session.display.append(DisplayMessage(kind="user", content=req.message))

    # Update teaching mode from request
    session.teaching_mode = req.teaching_mode

    events: list[dict] = []
    agent = _build_agent(session.workspace, on_event=lambda e: events.append(e), teaching_mode=session.teaching_mode)
    answer, _ = await agent.run(req.message, session.history)
    files = sessions.get_files(session_id)

    # Save tool events and answer to display history
    for event in events:
        if event.get("type") == "tool_result":
            session.display.append(DisplayMessage(
                kind="tool_event",
                tool=event.get("tool", ""),
                params=event.get("params", {}),
                result=event.get("result", ""),
            ))
    session.display.append(DisplayMessage(kind="assistant", content=answer))

    return {"answer": answer, "events": events, "files": files}


# --- Run code endpoint (for in-browser editor) ---

@app.post("/api/sessions/{session_id}/run")
async def run_code(session_id: str, req: RunRequest):
    """Save edited code to workspace and execute it."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Write the (possibly edited) content to the file
    target = (session.workspace / req.path).resolve()
    if not str(target).startswith(str(session.workspace.resolve())):
        raise HTTPException(400, "Invalid file path")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")

    # Execute using RunCodeTool
    runner = RunCodeTool(session.workspace)
    output = runner.execute(path=req.path)
    return {"output": output}


# --- WebSocket endpoint (streaming events) ---

@app.websocket("/api/sessions/{session_id}/ws")
async def websocket_chat(ws: WebSocket, session_id: str):
    await ws.accept()
    session = sessions.get(session_id)
    if not session:
        await ws.close(code=4004, reason="Session not found")
        return

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            user_message = msg.get("message", "")

            if not session.history:
                session.title = user_message[:50]

            async def send_event(event: dict):
                await ws.send_text(json.dumps(event))

            # We need to run the sync provider in a thread to avoid blocking
            events = []

            def collect_event(event: dict):
                events.append(event)

            agent = _build_agent(session.workspace, on_event=collect_event)
            answer, _ = await asyncio.to_thread(
                _run_agent_sync, agent, user_message, session.history
            )

            # Send all collected events
            for event in events:
                await ws.send_text(json.dumps(event))

            # Send final file list
            files = sessions.get_files(session_id)
            await ws.send_text(json.dumps({"type": "files", "files": files}))

    except WebSocketDisconnect:
        pass


def _run_agent_sync(agent: AgentLoop, message: str, history: list[dict]):
    """Run the async agent loop from a sync context (for threading)."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(agent.run(message, history))
    finally:
        loop.close()


# --- Serve frontend ---

FRONTEND_DIR = BASE_DIR / "frontend"

app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


@app.get("/")
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
