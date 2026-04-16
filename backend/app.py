"""FastAPI application — REST + WebSocket endpoints for c0der.

Endpoints:
  POST   /api/sessions                        Create a new session
  GET    /api/sessions                        List all sessions
  GET    /api/sessions/{id}/history           Get chat display history
  DELETE /api/sessions/{id}/history           Clear chat history
  GET    /api/sessions/{id}/files             List workspace files
  GET    /api/sessions/{id}/files/{path}      Read a workspace file
  POST   /api/sessions/{id}/chat             Send a message
  POST   /api/sessions/{id}/run              Run edited code
  POST   /api/sessions/{id}/connect-repo     Clone a GitHub repo into workspace
  WS     /api/sessions/{id}/ws               WebSocket for streaming events
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

from backend.agent.loop import AgentLoop, PROMPTS
from backend.agent.providers.base import Provider
from backend.agent.providers.claude import ClaudeProvider
from backend.agent.providers.gemini import GeminiProvider
from backend.agent.providers.openrouter import OpenRouterProvider
from backend.agent.tools.read_file import ReadFileTool
from backend.agent.tools.write_file import WriteFileTool
from backend.agent.tools.list_files import ListFilesTool
from backend.agent.tools.run_code import RunCodeTool
from backend.agent.tools.run_shell import RunShellTool
from backend.sessions.manager import SessionManager, DisplayMessage

load_dotenv()

app = FastAPI(title="c0der", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACES_DIR = BASE_DIR / "workspaces"
sessions = SessionManager(WORKSPACES_DIR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_provider() -> Provider:
    """Auto-detect which LLM provider to use based on environment variables.
    Priority: OPENROUTER_API_KEY > GEMINI_API_KEY > ANTHROPIC_API_KEY
    """
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    if openrouter_key:
        model = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
        return OpenRouterProvider(api_key=openrouter_key, model=model)
    elif gemini_key:
        return GeminiProvider(api_key=gemini_key)
    elif anthropic_key:
        return ClaudeProvider(api_key=anthropic_key)
    else:
        raise HTTPException(
            500,
            "No API key set. Add OPENROUTER_API_KEY, GEMINI_API_KEY, or "
            "ANTHROPIC_API_KEY to your .env file.",
        )


def _build_agent(session, on_event=None) -> AgentLoop:
    """Construct an agent bound to the given session's workspace."""
    provider = _get_provider()
    tools = [
        ReadFileTool(session.workspace),
        WriteFileTool(session.workspace),
        ListFilesTool(session.workspace),
        RunCodeTool(session.workspace),
        RunShellTool(session.workspace),
    ]
    system_prompt = PROMPTS.get(session.mode, PROMPTS["builder"])
    return AgentLoop(
        provider=provider, tools=tools, on_event=on_event, system_prompt=system_prompt
    )


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    mode: str = "builder"  # "builder" | "mentor" | "reviewer"


class RunRequest(BaseModel):
    path: str
    content: str


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@app.post("/api/sessions")
def create_session():
    session = sessions.create()
    return {"id": session.id, "title": session.title}


@app.get("/api/sessions")
def list_sessions():
    return sessions.list_all()


@app.get("/api/sessions/{session_id}/history")
def get_history(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return [
        {"kind": m.kind, "content": m.content,
         "tool": m.tool, "params": m.params, "result": m.result}
        for m in session.display
    ]


@app.delete("/api/sessions/{session_id}/history")
def clear_history(session_id: str):
    if not sessions.clear_history(session_id):
        raise HTTPException(404, "Session not found")
    return {"ok": True}


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


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    if not session.history:
        session.title = req.message[:50]

    session.mode = req.mode
    session.display.append(DisplayMessage(kind="user", content=req.message))

    events: list[dict] = []
    agent = _build_agent(session, on_event=lambda e: events.append(e))

    try:
        answer, _ = await agent.run(req.message, session.history)
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "rate" in err.lower() or "quota" in err.lower():
            raise HTTPException(429, "You've hit the rate limit or quota for this model. Wait a moment and try again, or use a different model.")
        if "401" in err or "403" in err or "authentication" in err.lower() or "api key" in err.lower():
            raise HTTPException(401, "Invalid API key. Check your .env file.")
        raise HTTPException(502, f"LLM error: {e}")

    for event in events:
        if event.get("type") == "tool_result":
            session.display.append(DisplayMessage(
                kind="tool_event",
                tool=event.get("tool", ""),
                params=event.get("params", {}),
                result=event.get("result", ""),
            ))
    session.display.append(DisplayMessage(kind="assistant", content=answer))

    return {"answer": answer, "events": events, "files": sessions.get_files(session_id)}


# ---------------------------------------------------------------------------
# Run code endpoint (in-browser editor)
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/run")
async def run_code(session_id: str, req: RunRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    target = (session.workspace / req.path).resolve()
    if not str(target).startswith(str(session.workspace.resolve())):
        raise HTTPException(400, "Invalid file path")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")

    runner = RunCodeTool(session.workspace)
    return {"output": runner.execute(path=req.path)}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

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

            events = []
            agent = _build_agent(session, on_event=lambda e: events.append(e))
            answer, _ = await asyncio.to_thread(
                _run_agent_sync, agent, user_message, session.history
            )
            for event in events:
                await ws.send_text(json.dumps(event))
            files = sessions.get_files(session_id)
            await ws.send_text(json.dumps({"type": "files", "files": files}))
    except WebSocketDisconnect:
        pass


def _run_agent_sync(agent, message, history):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(agent.run(message, history))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


@app.get("/")
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
