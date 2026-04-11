"""Abstract base class for agent tools."""

from abc import ABC, abstractmethod


class Tool(ABC):
    """A tool that the LLM can invoke during the agent loop.

    Each tool is self-describing: it carries its own name, description,
    and JSON Schema so the agent loop doesn't need to know tool details.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier sent to the LLM."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Natural-language description of what this tool does."""
        ...

    @property
    @abstractmethod
    def schema(self) -> dict:
        """JSON Schema for the tool's parameters."""
        ...

    @abstractmethod
    def execute(self, **params) -> str:
        """Run the tool and return a result string.

        Errors should be returned as strings (not raised), so the LLM
        can see and recover from them.
        """
        ...
