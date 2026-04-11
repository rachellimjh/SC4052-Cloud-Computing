"""Tool for reading files within the workspace."""

from pathlib import Path

from backend.agent.tools.base import Tool


class ReadFileTool(Tool):
    """Reads the contents of a file in the user's workspace."""

    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file at the given path. "
            "The path is relative to the project workspace."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file to read.",
                },
            },
            "required": ["path"],
        }

    def execute(self, **params) -> str:
        rel_path = params.get("path", "")
        target = (self.workspace / rel_path).resolve()

        # Prevent path traversal outside workspace
        if not str(target).startswith(str(self.workspace.resolve())):
            return "Error: Access denied — path is outside the workspace."

        if not target.exists():
            return f"Error: File not found: {rel_path}"
        if not target.is_file():
            return f"Error: Not a file: {rel_path}"

        try:
            return target.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"
