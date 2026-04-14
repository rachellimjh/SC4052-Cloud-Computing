"""Session management — one workspace per session.

Each session gets an isolated directory under workspaces/ where the agent
reads and writes files. Sessions also hold conversation history so the
agent can maintain context across multiple messages.
"""

import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DisplayMessage:
    """A message or tool event as shown in the frontend chat."""
    kind: str   # "user", "assistant", or "tool_event"
    content: str = ""
    tool: str = ""
    params: dict = field(default_factory=dict)
    result: str = ""


@dataclass
class Session:
    """A single user session with its own workspace and conversation."""
    id: str
    workspace: Path
    history: list[dict] = field(default_factory=list)
    display: list[DisplayMessage] = field(default_factory=list)
    title: str = "New Session"
    teaching_mode: bool = False


class SessionManager:
    """Creates and retrieves sessions, each backed by a workspace directory."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        """Create a new session with a fresh workspace."""
        session_id = uuid.uuid4().hex[:12]
        workspace = self.base_dir / session_id
        workspace.mkdir(parents=True, exist_ok=True)
        session = Session(id=session_id, workspace=workspace)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        """Retrieve an existing session by ID."""
        return self._sessions.get(session_id)

    def list_all(self) -> list[dict]:
        """Return summaries of all sessions."""
        return [
            {"id": s.id, "title": s.title, "messages": len(s.history)}
            for s in self._sessions.values()
        ]

    def get_files(self, session_id: str) -> list[str]:
        """List all files in a session's workspace."""
        session = self.get(session_id)
        if not session:
            return []
        files = []
        for path in sorted(session.workspace.rglob("*")):
            if path.is_file():
                files.append(str(path.relative_to(session.workspace)))
        return files

    def clear_history(self, session_id: str) -> bool:
        """Clear conversation and display history for a session (keeps workspace files)."""
        session = self.get(session_id)
        if not session:
            return False
        session.history.clear()
        session.display.clear()
        return True

    def read_file(self, session_id: str, rel_path: str) -> str | None:
        """Read a file from a session's workspace."""
        session = self.get(session_id)
        if not session:
            return None
        target = (session.workspace / rel_path).resolve()
        if not str(target).startswith(str(session.workspace.resolve())):
            return None
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8")
