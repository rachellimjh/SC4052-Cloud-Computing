"""Tool for listing files in the workspace."""

from pathlib import Path

from backend.agent.tools.base import Tool


class ListFilesTool(Tool):
    """Lists files and directories in the workspace."""

    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List all files and directories at the given path. "
            "The path is relative to the project workspace. "
            "Use an empty string to list the workspace root."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path to list. Use '' for root.",
                    "default": "",
                },
            },
        }

    def execute(self, **params) -> str:
        rel_path = params.get("path", "")
        target = (self.workspace / rel_path).resolve()

        if not str(target).startswith(str(self.workspace.resolve())):
            return "Error: Access denied — path is outside the workspace."

        if not target.exists():
            return f"Error: Directory not found: {rel_path or '.'}"
        if not target.is_dir():
            return f"Error: Not a directory: {rel_path}"

        try:
            entries = sorted(target.iterdir())
            lines = []
            for entry in entries:
                prefix = "[DIR] " if entry.is_dir() else "      "
                lines.append(f"{prefix}{entry.relative_to(self.workspace)}")
            return "\n".join(lines) if lines else "(empty directory)"
        except Exception as e:
            return f"Error listing files: {e}"
