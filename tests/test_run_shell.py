"""Tests for the RunShellTool."""

import pytest
from pathlib import Path
from backend.agent.tools.run_shell import RunShellTool


@pytest.fixture
def tool(tmp_path):
    return RunShellTool(workspace=tmp_path)


def test_simple_echo(tool):
    result = tool.execute(command="echo hello")
    assert "hello" in result


def test_stdout_and_stderr_captured(tool):
    # Write a script that prints to both stdout and stderr
    result = tool.execute(command='python -c "import sys; print(\'out\'); print(\'err\', file=sys.stderr)"')
    assert "out" in result
    assert "err" in result


def test_nonzero_exit_code_reported(tool):
    result = tool.execute(command="python -c \"raise SystemExit(1)\"")
    assert "Exit code: 1" in result


def test_empty_command_returns_error(tool):
    result = tool.execute(command="")
    assert "Error" in result


def test_timeout(tmp_path):
    tool = RunShellTool(workspace=tmp_path, timeout=1)
    result = tool.execute(command="python -c \"import time; time.sleep(10)\"")
    assert "timed out" in result.lower()


def test_runs_in_workspace(tool, tmp_path):
    # Write a file and check the command sees it
    (tmp_path / "sentinel.txt").write_text("found")
    result = tool.execute(command="python -c \"print(open('sentinel.txt').read())\"")
    assert "found" in result


def test_runs_pytest(tool, tmp_path):
    # Write a trivial passing test and run pytest
    (tmp_path / "test_trivial.py").write_text("def test_ok(): assert 1 + 1 == 2\n")
    result = tool.execute(command="python -m pytest test_trivial.py -v")
    assert "passed" in result


def test_runs_pytest_failing_test(tool, tmp_path):
    (tmp_path / "test_fail.py").write_text("def test_bad(): assert False\n")
    result = tool.execute(command="python -m pytest test_fail.py -v")
    assert "failed" in result
    assert "Exit code" in result
