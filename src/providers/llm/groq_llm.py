"""Groq LLM provider using Llama / Scorpion models."""

import os

from groq import Groq, APIError, AuthenticationError, RateLimitError

from src.providers.llm.base import LLMProvider, LLMResponse
from src.utils.errors import PermanentProviderError, TransientProviderError
from src.utils.logger import get_logger
from src.utils.retry import RetryPolicy

logger = get_logger(__name__)

# Default model
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqLLMProvider(LLMProvider):
    """LLM provider using Groq's fast inference engine.

    Supports Llama 4 / Scorpion models and JSON response format.
    """

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self._api_key:
            raise PermanentProviderError(
                "Groq API key not provided. Set GROQ_API_KEY environment variable "
                "or pass api_key to the constructor."
            )
        self._model = model
        self._client: Groq | None = None

    @property
    def name(self) -> str:
        return "groq"

    @property
    def model(self) -> str:
        return self._model

    def _get_client(self) -> Groq:
        """Lazy initialization of the Groq client."""
        if self._client is None:
            self._client = Groq(api_key=self._api_key)
        return self._client

    def supports_json_mode(self) -> bool:
        """Groq supports JSON-structured output."""
        return True

    @RetryPolicy(max_retries=2, base_delay=1.0, max_delay=10.0).retry
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Generate a completion using Groq.

        Args:
            prompt: User prompt / main input text.
            system_prompt: Optional system-level instructions.
            response_format: Set to "json" for JSON-structured output.

        Returns:
            LLMResponse with generated text and usage metadata.

        Raises:
            TransientProviderError: Rate limit or server errors (retryable).
            PermanentProviderError: Auth errors or invalid requests (not retryable).
        """
        client = self._get_client()

        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Build request kwargs
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
        }

        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            raise TransientProviderError(
                f"Groq rate limit exceeded: {e}", status_code=429
            ) from e
        except AuthenticationError as e:
            raise PermanentProviderError(
                f"Groq authentication failed: {e}", status_code=401
            ) from e
        except APIError as e:
            status = getattr(e, "status_code", None)
            if status and 500 <= status < 600:
                raise TransientProviderError(
                    f"Groq server error: {e}", status_code=status
                ) from e
            raise PermanentProviderError(
                f"Groq API error: {e}", status_code=status
            ) from e

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            text=choice.message.content or "",
            usage={
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            },
            provider=self.name,
            model=self._model,
            finish_reason=choice.finish_reason,
        )
