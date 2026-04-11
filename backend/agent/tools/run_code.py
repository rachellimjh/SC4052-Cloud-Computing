"""Tool for running Python code in a Docker container.

This is the 'cloud' in Coding-as-a-Service — user code runs inside a
disposable container with no network access, limited memory, and a hard
timeout. The session workspace is bind-mounted read/write so the code
can read its own files and produce output files.

Falls back to subprocess execution when Docker is unavailable (e.g. local
development without Docker installed).
"""

import subprocess
import shutil
from pathlib import Path

from backend.agent.tools.base import Tool

DOCKER_IMAGE = "vibecoder-sandbox"


def _check_docker_ready() -> bool:
    """Check if Docker is installed AND the sandbox image exists."""
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


DOCKER_READY = _check_docker_ready()


class RunCodeTool(Tool):
    """Executes a Python file in a Docker sandbox (or subprocess fallback)."""

    def __init__(self, workspace: Path, timeout: int = 15):
        self.workspace = workspace
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "run_python"

    @property
    def description(self) -> str:
        return (
            "Run a Python file in a sandboxed environment and return its output. "
            "The file path is relative to the workspace. "
            f"Execution is limited to {self.timeout} seconds."
        )

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the Python file to run.",
                },
            },
            "required": ["path"],
        }

    def execute(self, **params) -> str:
        rel_path = params.get("path", "")
        target = (self.workspace / rel_path).resolve()

        if not str(target).startswith(str(self.workspace.resolve())):
            return "Error: Access denied — path is outside the workspace."
        if not target.exists():
            return f"Error: File not found: {rel_path}"
        if not target.suffix == ".py":
            return "Error: Only .py files can be executed."

        if DOCKER_READY:
            result = self._run_in_docker(rel_path)
            # Fall back to subprocess if Docker fails unexpectedly
            if result.startswith("Error running in Docker:"):
                return self._run_in_subprocess(rel_path)
            return result
        return self._run_in_subprocess(rel_path)

    def _run_in_docker(self, rel_path: str) -> str:
        """Run code inside a Docker container with security constraints."""
        workspace_posix = str(self.workspace.resolve()).replace("\\", "/")
        cmd = [
            "docker", "run",
            "--rm",                             # remove container after exit
            "--network", "none",                # no internet access
            "--memory", "128m",                 # cap memory at 128 MB
            "--cpus", "0.5",                    # half a CPU core
            "--pids-limit", "32",               # limit process spawning
            "--read-only",                      # read-only root filesystem
            "--tmpfs", "/tmp:size=32m",          # writable /tmp for scratch
            "-v", f"{workspace_posix}:/workspace",  # mount user files
            "-w", "/workspace",                 # working directory
            DOCKER_IMAGE,
            "python", rel_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 5,  # extra margin for container startup
            )
            return self._format_output(result)
        except subprocess.TimeoutExpired:
            # Kill the container if it's still running
            subprocess.run(
                ["docker", "kill", f"vibecoder-{id(self)}"],
                capture_output=True, timeout=5,
            )
            return f"Error: Execution timed out after {self.timeout} seconds."
        except Exception as e:
            return f"Error running in Docker: {e}"

    def _run_in_subprocess(self, rel_path: str) -> str:
        """Fallback: run code as a local subprocess (no Docker)."""
        target = self.workspace / rel_path
        try:
            result = subprocess.run(
                ["python", str(target)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.workspace),
            )
            return self._format_output(result)
        except subprocess.TimeoutExpired:
            return f"Error: Execution timed out after {self.timeout} seconds."
        except Exception as e:
            return f"Error running code: {e}"

    def _format_output(self, result: subprocess.CompletedProcess) -> str:
        """Format stdout/stderr/exit code into a single result string."""
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr
        if result.returncode != 0:
            output += f"\n[Exit code: {result.returncode}]"
        return output.strip() or "(no output)"
