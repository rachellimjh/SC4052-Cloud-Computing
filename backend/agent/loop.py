"""Core agent loop — the think-act-observe cycle.

This is the heart of the coding agent. It sends the conversation to the
LLM, checks if the LLM wants to call tools, executes them, appends the
results, and repeats until the LLM produces a final text-only answer.

The loop mirrors the architecture described in Ben Recht's microagent
(https://github.com/benjamin-recht/microagent) but adds a system prompt,
iteration limits, and streaming callbacks for the web UI.
"""

from typing import Callable

from backend.agent.models import ToolCall
from backend.agent.providers.base import Provider
from backend.agent.tools.base import Tool

SYSTEM_PROMPT = """\
You are c0der, a friendly AI coding assistant designed for beginners.
Your job is to help users build software by writing code for them based on
natural-language descriptions (vibe coding).

Guidelines:
- Write clean, well-commented Python code that a beginner can understand.
- When you create or modify files, ALWAYS use the write_file tool.
- Before writing code, briefly explain your plan in plain English.
- After writing code, run it with run_python to verify it works.
- If there are errors, read the output, fix the code, and re-run.
- Keep explanations short and jargon-free.
- When asked to explain code, break it down line by line.
- Organize code into separate files when appropriate.
- Use list_files to see what's already in the workspace.

You have these tools available:
- read_file: Read an existing file
- write_file: Create or overwrite a file
- list_files: List files in the workspace
- run_python: Execute a Python file and see the output
"""

TEACHING_SYSTEM_PROMPT = """\
You are c0der, a friendly AI coding assistant running in TEACHING MODE.
Your job is to help beginners learn to code by writing code AND explaining
every single line so they understand what's happening.

Guidelines:
- When you write code, add a detailed comment above EVERY line or block
  explaining what it does and WHY, in plain beginner-friendly language.
- After writing the file, provide a "Line-by-Line Walkthrough" section
  in your response that explains the code step by step, like a tutor
  sitting next to the student.
- Use analogies and real-world comparisons to explain programming concepts.
- Highlight common beginner mistakes related to the code you wrote.
- When you create or modify files, ALWAYS use the write_file tool.
- Before writing code, explain your plan in plain English.
- After writing code, run it with run_python to verify it works.
- If there are errors, explain what the error means in beginner terms,
  then fix it and re-run.
- Organize code into separate files when appropriate.
- Use list_files to see what's already in the workspace.

You have these tools available:
- read_file: Read an existing file
- write_file: Create or overwrite a file
- list_files: List files in the workspace
- run_python: Execute a Python file and see the output
"""

MAX_ITERATIONS = 25


class AgentLoop:
    """Runs the LLM agent loop with tool execution.

    Args:
        provider: The LLM provider to use (e.g. ClaudeProvider).
        tools: List of Tool instances available to the agent.
        on_event: Optional callback for streaming events to the frontend.
    """

    def __init__(
        self,
        provider: Provider,
        tools: list[Tool],
        on_event: Callable[[dict], None] | None = None,
        system_prompt: str | None = None,
    ):
        self.provider = provider
        self.tools = tools
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self._tool_map = {tool.name: tool for tool in tools}
        self._on_event = on_event or (lambda e: None)

    async def run(self, task: str, history: list[dict]) -> tuple[str, list[dict]]:
        """Execute the agent loop for a user task.

        Args:
            task: The user's natural-language request.
            history: Existing conversation history (mutated in place).

        Returns:
            A tuple of (final_answer, updated_history).
        """
        history.append({"role": "user", "content": task})

        for iteration in range(MAX_ITERATIONS):
            self._emit("thinking", {"iteration": iteration + 1})

            response = self.provider.chat(self.system_prompt, history, self.tools)

            if response.is_final:
                history.append({"role": "assistant", "content": response.content})
                self._emit("answer", {"content": response.content})
                return response.content, history

            # Append the assistant's message (with tool calls) to history
            history.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "parameters": tc.parameters}
                    for tc in response.tool_calls
                ],
            })

            if response.content:
                self._emit("thinking_text", {"content": response.content})

            # Execute each tool call and append results
            for tc in response.tool_calls:
                result = self._execute_tool(tc)
                history.append({
                    "role": "tool",
                    "tool_use_id": tc.id,
                    "content": result,
                })
                self._emit("tool_result", {
                    "tool": tc.name,
                    "params": tc.parameters,
                    "result": result,
                })

        # Iteration limit reached
        fallback = "I've reached the maximum number of steps. Here's what I have so far."
        history.append({"role": "assistant", "content": fallback})
        self._emit("answer", {"content": fallback})
        return fallback, history

    def _execute_tool(self, tool_call: ToolCall) -> str:
        """Dispatch a tool call and return the result string."""
        tool = self._tool_map.get(tool_call.name)
        if not tool:
            return f"Error: Unknown tool '{tool_call.name}'"
        try:
            return tool.execute(**tool_call.parameters)
        except Exception as e:
            return f"Error executing {tool_call.name}: {e}"

    def _emit(self, event_type: str, data: dict):
        """Send an event to the frontend callback."""
        self._on_event({"type": event_type, **data})
