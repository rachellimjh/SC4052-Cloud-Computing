"""Abstract base for LLM providers."""

from abc import ABC, abstractmethod

from backend.agent.models import Response


class Provider(ABC):
    """Protocol that any LLM provider must implement."""

    @abstractmethod
    def chat(self, system_prompt: str, messages: list[dict], tools: list) -> Response:
        """Send a conversation to the LLM and return its response.

        Args:
            system_prompt: The system-level instruction for the LLM.
            messages: Conversation history in the internal format.
            tools: List of Tool objects available to the LLM.

        Returns:
            A Response containing the LLM's text and any tool calls.
        """
        ...
