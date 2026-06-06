"""DeepSeek LLM provider using OpenAI-compatible API."""

import os

from openai import OpenAI, APIError, AuthenticationError, RateLimitError

from src.providers.llm.base import LLMProvider, LLMResponse
from src.utils.errors import PermanentProviderError, TransientProviderError
from src.utils.logger import get_logger
from src.utils.retry import RetryPolicy

logger = get_logger(__name__)

# DeepSeek API base URL (OpenAI-compatible)
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# Default model
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekLLMProvider(LLMProvider):
    """LLM provider using DeepSeek's OpenAI-compatible API.

    Supports v4 Flash model and JSON response format.
    """

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self._api_key:
            raise PermanentProviderError(
                "DeepSeek API key not provided. Set DEEPSEEK_API_KEY environment variable "
                "or pass api_key to the constructor."
            )
        self._model = model
        self._client: OpenAI | None = None

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def model(self) -> str:
        return self._model

    def _get_client(self) -> OpenAI:
        """Lazy initialization of the OpenAI-compatible client."""
        if self._client is None:
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=DEEPSEEK_BASE_URL,
            )
        return self._client

    def supports_json_mode(self) -> bool:
        """DeepSeek supports JSON-structured output."""
        return True

    @RetryPolicy(max_retries=2, base_delay=1.0, max_delay=10.0).retry
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Generate a completion using DeepSeek.

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
                f"DeepSeek rate limit exceeded: {e}", status_code=429
            ) from e
        except AuthenticationError as e:
            raise PermanentProviderError(
                f"DeepSeek authentication failed: {e}", status_code=401
            ) from e
        except APIError as e:
            status = getattr(e, "status_code", None)
            if status and 500 <= status < 600:
                raise TransientProviderError(
                    f"DeepSeek server error: {e}", status_code=status
                ) from e
            raise PermanentProviderError(
                f"DeepSeek API error: {e}", status_code=status
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
