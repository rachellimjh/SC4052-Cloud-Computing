"""Tests for session management endpoints.

Covers: create, list, history, clear-history, file listing, and file reading.
Uses FastAPI's TestClient (synchronous HTTPX) — no real LLM calls are made.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def test_create_session_returns_id_and_title():
    res = client.post("/api/sessions")
    assert res.status_code == 200
    data = res.json()
    assert "id" in data
    assert "title" in data


def test_list_sessions_includes_created_session():
    create_res = client.post("/api/sessions")
    session_id = create_res.json()["id"]

    list_res = client.get("/api/sessions")
    assert list_res.status_code == 200
    ids = [s["id"] for s in list_res.json()]
    assert session_id in ids


# ---------------------------------------------------------------------------
# History endpoints
# ---------------------------------------------------------------------------

def test_get_history_empty_on_new_session():
    session_id = client.post("/api/sessions").json()["id"]
    res = client.get(f"/api/sessions/{session_id}/history")
    assert res.status_code == 200
    assert res.json() == []


def test_get_history_unknown_session_returns_404():
    res = client.get("/api/sessions/does-not-exist/history")
    assert res.status_code == 404


def test_clear_history_returns_ok():
    session_id = client.post("/api/sessions").json()["id"]
    res = client.delete(f"/api/sessions/{session_id}/history")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_clear_history_empties_display_messages(monkeypatch):
    """After clearing, GET /history should return an empty list."""
    from backend.app import sessions
    from backend.sessions.manager import DisplayMessage

    session_id = client.post("/api/sessions").json()["id"]
    session = sessions.get(session_id)

    # Manually inject display messages (simulates a prior conversation)
    session.display.append(DisplayMessage(kind="user", content="hello"))
    session.display.append(DisplayMessage(kind="assistant", content="hi there"))

    # Verify they're present
    history_before = client.get(f"/api/sessions/{session_id}/history").json()
    assert len(history_before) == 2

    # Clear and verify
    client.delete(f"/api/sessions/{session_id}/history")
    history_after = client.get(f"/api/sessions/{session_id}/history").json()
    assert history_after == []


def test_clear_history_also_resets_agent_history(monkeypatch):
    """Clearing should reset the LLM conversation history too."""
    from backend.app import sessions

    session_id = client.post("/api/sessions").json()["id"]
    session = sessions.get(session_id)
    session.history.append({"role": "user", "content": "test"})

    client.delete(f"/api/sessions/{session_id}/history")
    assert session.history == []


def test_clear_history_unknown_session_returns_404():
    res = client.delete("/api/sessions/does-not-exist/history")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# File endpoints
# ---------------------------------------------------------------------------

def test_list_files_empty_on_new_session():
    session_id = client.post("/api/sessions").json()["id"]
    res = client.get(f"/api/sessions/{session_id}/files")
    assert res.status_code == 200
    assert res.json() == []


def test_list_files_unknown_session_returns_404():
    res = client.get("/api/sessions/does-not-exist/files")
    assert res.status_code == 404


def test_read_file_after_write(tmp_path):
    """Writing a file to the workspace makes it readable via the API."""
    from backend.app import sessions

    session_id = client.post("/api/sessions").json()["id"]
    session = sessions.get(session_id)

    # Write a file directly into the workspace (simulates agent write_file)
    (session.workspace / "hello.py").write_text("print('hello')", encoding="utf-8")

    res = client.get(f"/api/sessions/{session_id}/files/hello.py")
    assert res.status_code == 200
    data = res.json()
    assert data["path"] == "hello.py"
    assert data["content"] == "print('hello')"


def test_read_file_not_found_returns_404():
    session_id = client.post("/api/sessions").json()["id"]
    res = client.get(f"/api/sessions/{session_id}/files/nope.py")
    assert res.status_code == 404


def test_clear_history_preserves_workspace_files():
    """Clearing history must NOT delete files from the workspace."""
    from backend.app import sessions

    session_id = client.post("/api/sessions").json()["id"]
    session = sessions.get(session_id)
    (session.workspace / "keep.py").write_text("x = 1", encoding="utf-8")

    client.delete(f"/api/sessions/{session_id}/history")

    res = client.get(f"/api/sessions/{session_id}/files/keep.py")
    assert res.status_code == 200
    assert res.json()["content"] == "x = 1"
