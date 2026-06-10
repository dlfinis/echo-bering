"""LLM provider domain models and abstract interface.

LLMResponse is the shared data structure returned by all LLM providers.
LLMProvider is the abstract interface for provider implementations.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Structured response from an LLM provider."""

    text: str
    usage: dict
    provider: str
    model: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    finish_reason: str | None = None


class LLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Generate a completion from the LLM.

        Args:
            prompt: User prompt / main input text.
            system_prompt: Optional system-level instructions.
            response_format: Optional format hint (e.g. "json") for structured output.

        Returns:
            LLMResponse with generated text and metadata.
        """
        ...

    @abstractmethod
    def supports_json_mode(self) -> bool:
        """Whether this provider supports JSON-structured response format."""
        ...
