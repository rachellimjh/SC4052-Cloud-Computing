"""OpenRouter provider — OpenAI-compatible API for 100+ models.

OpenRouter proxies many model providers through a single OpenAI-compatible
endpoint, so this provider works for any model available on openrouter.ai.

Set in .env:
  OPENROUTER_API_KEY=sk-or-...
  OPENROUTER_MODEL=google/gemma-4-31b-it:free   # optional, this is the default
"""

import json
import time
import openai

from backend.agent.models import Response, ToolCall
from backend.agent.providers.base import Provider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(Provider):
    """Wraps any OpenRouter model via the OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemma-4-31b-it:free",
    ):
        self.model = model
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )

    def chat(self, system_prompt: str, messages: list[dict], tools: list) -> Response:
        """Send conversation to OpenRouter and parse the response."""
        oai_messages = self._convert_messages(system_prompt, messages)
        oai_tools = [self._convert_tool(t) for t in tools]

        kwargs = dict(
            model=self.model,
            messages=oai_messages,
            max_tokens=4096,
        )
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(**kwargs)
                return self._parse_response(response)
            except openai.RateLimitError:
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))  # 5s, then 10s
                else:
                    return Response(
                        content=(
                            f"The model `{self.model}` is currently rate-limited "
                            "by the upstream provider. Try again in a moment, or switch "
                            "to a different model by changing OPENROUTER_MODEL in your .env — "
                            "e.g. `mistralai/mistral-small-3.2-24b-instruct:free`."
                        ),
                        tool_calls=[],
                    )
            except openai.APIError as e:
                return Response(content=f"OpenRouter API error: {e}", tool_calls=[])

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def _convert_tool(self, tool) -> dict:
        """Convert an internal Tool to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.schema,
            },
        }

    def _convert_messages(
        self, system_prompt: str, messages: list[dict]
    ) -> list[dict]:
        """Convert internal history format to OpenAI messages.

        OpenAI message roles:
          system   — one at the top
          user     — human turn
          assistant — model turn (may include tool_calls)
          tool     — tool result (role="tool", tool_call_id=...)
        """
        converted: list[dict] = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            role = msg["role"]

            if role == "user":
                converted.append({"role": "user", "content": msg["content"]})

            elif role == "assistant":
                entry: dict = {"role": "assistant", "content": msg.get("content") or ""}
                tcs = msg.get("tool_calls", [])
                if tcs:
                    entry["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["parameters"]),
                            },
                        }
                        for tc in tcs
                    ]
                converted.append(entry)

            elif role == "tool":
                converted.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_use_id"],
                    "content": msg["content"],
                })

        return converted

    def _parse_response(self, response) -> Response:
        """Extract text and tool calls from the OpenAI-format response."""
        choice = response.choices[0]
        msg = choice.message

        text = msg.content or ""
        tool_calls: list[ToolCall] = []

        for tc in msg.tool_calls or []:
            try:
                params = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                params = {}
            tool_calls.append(ToolCall(
                name=tc.function.name,
                parameters=params,
                id=tc.id,
            ))

        return Response(content=text, tool_calls=tool_calls)
