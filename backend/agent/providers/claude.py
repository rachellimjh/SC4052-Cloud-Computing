"""Claude API provider using the Anthropic SDK."""

import anthropic

from backend.agent.models import Response, ToolCall
from backend.agent.providers.base import Provider


class ClaudeProvider(Provider):
    """Wraps the Anthropic Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(self, system_prompt: str, messages: list[dict], tools: list) -> Response:
        """Send conversation to Claude and parse the response."""
        claude_messages = self._convert_messages(messages)
        claude_tools = [self._convert_tool(t) for t in tools]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=claude_messages,
            tools=claude_tools,
        )

        return self._parse_response(response)

    def _convert_tool(self, tool) -> dict:
        """Convert an internal Tool to Claude's tool format."""
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.schema,
        }

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert internal message format to Claude's API format.

        Claude requires tool results to be sent as user messages with
        content blocks of type 'tool_result', and assistant tool calls
        as content blocks of type 'tool_use'.
        """
        converted = []

        for msg in messages:
            role = msg["role"]

            if role == "user":
                converted.append({"role": "user", "content": msg["content"]})

            elif role == "assistant":
                content_blocks = []
                if msg.get("content"):
                    content_blocks.append({"type": "text", "text": msg["content"]})
                for tc in msg.get("tool_calls", []):
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["parameters"],
                    })
                converted.append({"role": "assistant", "content": content_blocks})

            elif role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg["tool_use_id"],
                        "content": msg["content"],
                    }],
                })

        return converted

    def _parse_response(self, response) -> Response:
        """Extract text and tool calls from Claude's response."""
        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    name=block.name,
                    parameters=block.input,
                    id=block.id,
                ))

        return Response(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
        )
