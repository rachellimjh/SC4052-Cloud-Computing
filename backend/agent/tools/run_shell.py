"""Tool for running arbitrary shell commands in the session workspace.

This enables the agent to run tests, use git, call the GitHub API, and
perform any other shell-based workflow step. Commands execute inside the
workspace directory with a configurable timeout.
"""

import subprocess
from pathlib import Path

from backend.agent.tools.base import Tool


class RunShellTool(Tool):
    """Runs a shell command in the workspace and returns the output."""

    def __init__(self, workspace: Path, timeout: int = 30):
        self.workspace = workspace
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "run_shell"

    @property
    def description(self) -> str:
        return (
            "Run any shell command inside the workspace directory and return its output "
            "(stdout + stderr). Use this to run tests (e.g. 'pytest -v'), use git "
            "('git init', 'git checkout -b feature/x', 'git add -A', 'git commit -m ...', "
            "'git push origin branch'), or create a GitHub PR via the API. "
            f"Commands time out after {self.timeout} seconds."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                },
            },
            "required": ["command"],
        }

    def execute(self, **params) -> str:
        command = params.get("command", "").strip()
        if not command:
            return "Error: No command provided."

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.workspace),
            )
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += ("\n[STDERR]\n" if result.stdout else "") + result.stderr
            if result.returncode != 0:
                output += f"\n[Exit code: {result.returncode}]"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {self.timeout} seconds."
        except Exception as e:
            return f"Error running command: {e}"
