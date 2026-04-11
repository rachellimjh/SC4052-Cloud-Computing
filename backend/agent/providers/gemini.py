"""Google Gemini API provider using the google-genai SDK."""

from google import genai
from google.genai import types

from backend.agent.models import Response, ToolCall
from backend.agent.providers.base import Provider


class GeminiProvider(Provider):
    """Wraps the Google Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def chat(self, system_prompt: str, messages: list[dict], tools: list) -> Response:
        """Send conversation to Gemini and parse the response."""
        gemini_tools = self._build_tools(tools)
        gemini_contents = self._convert_messages(messages)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=gemini_tools,
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="AUTO",
                ),
            ),
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=gemini_contents,
            config=config,
        )

        return self._parse_response(response)

    def _build_tools(self, tools: list) -> list[types.Tool]:
        """Convert internal Tool objects to Gemini function declarations."""
        declarations = []
        for tool in tools:
            schema = tool.schema.copy()
            declarations.append(types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=schema,
            ))
        return [types.Tool(function_declarations=declarations)]

    def _convert_messages(self, messages: list[dict]) -> list[types.Content]:
        """Convert internal message format to Gemini contents.

        Gemini requires strictly alternating user/model roles. Multiple
        consecutive tool results (which are user-role) must be merged
        into a single Content with multiple parts.
        """
        contents: list[types.Content] = []

        for msg in messages:
            role = msg["role"]

            if role == "user":
                parts = [types.Part.from_text(text=msg["content"])]
                self._append_or_merge(contents, "user", parts)

            elif role == "assistant":
                parts = []
                if msg.get("content"):
                    parts.append(types.Part.from_text(text=msg["content"]))
                for tc in msg.get("tool_calls", []):
                    parts.append(types.Part.from_function_call(
                        name=tc["name"],
                        args=tc["parameters"],
                    ))
                self._append_or_merge(contents, "model", parts)

            elif role == "tool":
                tool_name = self._find_tool_name(messages, msg["tool_use_id"])
                parts = [types.Part.from_function_response(
                    name=tool_name,
                    response={"result": msg["content"]},
                )]
                self._append_or_merge(contents, "user", parts)

        return contents

    def _append_or_merge(
        self, contents: list[types.Content], role: str, parts: list
    ):
        """Append parts to the last Content if same role, else create new."""
        gemini_role = role if role == "user" else "model"
        if contents and contents[-1].role == gemini_role:
            # Merge into existing Content
            contents[-1].parts.extend(parts)
        else:
            contents.append(types.Content(role=gemini_role, parts=parts))

    def _find_tool_name(self, messages: list[dict], tool_use_id: str) -> str:
        """Find the tool name for a given tool_use_id by scanning history."""
        for msg in messages:
            for tc in msg.get("tool_calls", []):
                if tc["id"] == tool_use_id:
                    return tc["name"]
        return "unknown"

    def _parse_response(self, response) -> Response:
        """Extract text and tool calls from Gemini's response."""
        text_parts = []
        tool_calls = []

        if not response.candidates:
            return Response(content="No response from Gemini.", tool_calls=[])

        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if part.text:
                text_parts.append(part.text)
            elif part.function_call:
                fc = part.function_call
                tool_calls.append(ToolCall(
                    name=fc.name,
                    parameters=dict(fc.args) if fc.args else {},
                    id=f"gemini_{fc.name}_{len(tool_calls)}",
                ))

        return Response(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
        )
