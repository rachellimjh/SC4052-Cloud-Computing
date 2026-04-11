"""Data models for the agent system."""

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """Represents a tool call requested by the LLM."""
    name: str
    parameters: dict
    id: str


@dataclass
class Response:
    """Represents an LLM response, possibly containing tool calls."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        """A response is final when the LLM made no tool calls."""
        return len(self.tool_calls) == 0
