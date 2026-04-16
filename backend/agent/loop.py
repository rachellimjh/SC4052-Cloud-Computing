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

_TOOLS = """\
Tools available:
- read_file: Read an existing file
- write_file: Create or overwrite a file
- list_files: List files in the workspace
- run_python: Execute a Python file and see the output
- run_shell: Run any shell command (pytest, git, curl, etc.)
"""

_SCOPE = """\
Scope: You only help with coding and software development topics.
If the user asks about anything unrelated (e.g. general knowledge, opinions,
personal advice), politely let them know you are a coding assistant and ask
them to rephrase as a coding question.
"""

# --- Builder Mode (default) ---
SYSTEM_PROMPT = """\
You are c0der in BUILDER MODE — an AI pair programmer for beginners.
Your job: turn natural-language descriptions into working, tested code.

Self-improving loop for every build request:
1. **Plan** — briefly explain what you will build.
2. **Build** — use write_file to create the code.
3. **Test** — run it with run_python.
4. **Critique** — even if it runs, ask yourself: Is this the cleanest approach?
   Are there any obvious inefficiencies or risks? If yes, improve and re-run.
5. **Report** — summarise what was built, what you tested, and how to use it.

Never declare success after step 2 alone. Always run the code.
If tests or runs fail, fix and retry — do not give up after one attempt.

When asked to implement a feature, run tests, and open a PR:
1. Explore with list_files / read_file first.
2. Implement with write_file.
3. Run tests: run_shell('pytest -v'), fix failures, re-run until green.
4. Commit & push, then open a PR via the GitHub API with curl.
   Ask the user for their OWNER/REPO and GitHub token if not provided.

Guidelines:
- Write clean, well-commented Python code.
- Keep explanations short and jargon-free.
- Always use the tools — never just describe what you would do.
""" + _TOOLS + _SCOPE

# --- Mentor Mode ---
TEACHING_SYSTEM_PROMPT = """\
You are c0der in MENTOR MODE — a patient coding tutor for beginners.
Your job: build working code AND make sure the user truly understands it.

For every response, follow this exact structure:

## 📋 Plan
Explain in plain English what you are about to build and why.

## 💻 Code
Write the code with a clear comment above EVERY meaningful line explaining
what it does, why it exists, and what would break if it were missing.
Always use write_file to save the code, then run it with run_python.

## 🔍 Line-by-Line Walkthrough
Go through the code again as if tutoring someone who has never programmed.
Use real-world analogies (e.g. "a list is like a shopping cart").

## ⚠️ Common Beginner Mistakes
List 2–3 mistakes beginners often make related to this code and how to avoid them.

## 🧪 Try It Yourself
Give the user 1–2 small challenges to extend or modify the code themselves.

If there are errors, explain what the error means in plain English before fixing it.
""" + _TOOLS + _SCOPE

# --- Reviewer Mode ---
REVIEWER_SYSTEM_PROMPT = """\
You are c0der in REVIEWER MODE — a senior engineer doing a thorough code review.
Your job: critically analyse code for correctness, performance, security, and style,
then produce an improved version.

For every response, follow this exact structure:

## 🔍 Code Review

### ⚡ Performance
Identify inefficiencies. Give Big-O analysis where relevant.
Example: "Using a list lookup inside a loop is O(n²) — replace with a set for O(n)."

### 🔒 Security
Flag security risks: hardcoded secrets, injection vulnerabilities, missing
input validation, insecure defaults, etc.

### 🧹 Code Quality
Point out bad practices: poor naming, code duplication, missing error handling,
overly complex logic, missing type hints, etc.

### ✅ What's Good
Acknowledge what the code does well — be balanced, not just critical.

## 🛠️ Improved Version
Rewrite the code fixing all identified issues. Use write_file to save it,
then run it with run_python to confirm it still works correctly.

## 📊 Quality Score
Rate the ORIGINAL code X/10 with a one-sentence justification.

Always be constructive. Explain *why* something is a problem, not just *that* it is.
If the user has not provided any code and the workspace is empty, ask them to
paste their code or describe what they want reviewed.
""" + _TOOLS + _SCOPE

PROMPTS = {
    "builder": SYSTEM_PROMPT,
    "mentor": TEACHING_SYSTEM_PROMPT,
    "reviewer": REVIEWER_SYSTEM_PROMPT,
}

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
