"""Tool for writing files within the workspace."""

from pathlib import Path

from backend.agent.tools.base import Tool


class WriteFileTool(Tool):
    """Creates or overwrites a file in the user's workspace."""

    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file at the given path. "
            "Creates parent directories if needed. "
            "The path is relative to the project workspace."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file.",
                },
            },
            "required": ["path", "content"],
        }

    def execute(self, **params) -> str:
        rel_path = params.get("path", "")
        content = params.get("content", "")
        target = (self.workspace / rel_path).resolve()

        if not str(target).startswith(str(self.workspace.resolve())):
            return "Error: Access denied — path is outside the workspace."

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} bytes to {rel_path}"
        except Exception as e:
            return f"Error writing file: {e}"
