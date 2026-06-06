"""OpenAI ASR provider using Whisper model."""

import os
from pathlib import Path

from openai import OpenAI, APIError, AuthenticationError, RateLimitError

from src.providers.asr.base import ASRProvider, TranscriptResult, WordTimestamp
from src.utils.errors import PermanentProviderError, TransientProviderError
from src.utils.logger import get_logger
from src.utils.retry import RetryPolicy

logger = get_logger(__name__)

# OpenAI Whisper file size limit: 25 MB
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

# Default model
DEFAULT_MODEL = "whisper-1"


class OpenAIASRProvider(ASRProvider):
    """ASR provider using OpenAI's Whisper model.

    Serves as a fallback provider with reliable Whisper support.
    Basic transcription without word-level timestamps.
    """

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise PermanentProviderError(
                "OpenAI API key not provided. Set OPENAI_API_KEY environment variable "
                "or pass api_key to the constructor."
            )
        self._model = model
        self._client: OpenAI | None = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    def _get_client(self) -> OpenAI:
        """Lazy initialization of the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    @RetryPolicy(max_retries=2, base_delay=1.0, max_delay=10.0).retry
    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe audio file using OpenAI Whisper.

        Args:
            audio_path: Path to the audio file (WAV, MP3, M4A, etc.).

        Returns:
            TranscriptResult with text and metadata.
            Note: OpenAI basic API does not return word-level timestamps.

        Raises:
            TransientProviderError: Rate limit or server errors (retryable).
            PermanentProviderError: Auth errors or invalid requests (not retryable).
        """
        path = Path(audio_path)
        if not path.exists():
            raise PermanentProviderError(f"Audio file not found: {audio_path}")

        client = self._get_client()

        try:
            with open(path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    file=audio_file,
                    model=self._model,
                    response_format="text",
                    language="es",
                )
        except RateLimitError as e:
            raise TransientProviderError(
                f"OpenAI rate limit exceeded: {e}", status_code=429
            ) from e
        except AuthenticationError as e:
            raise PermanentProviderError(
                f"OpenAI authentication failed: {e}", status_code=401
            ) from e
        except APIError as e:
            status = getattr(e, "status_code", None)
            if status and 500 <= status < 600:
                raise TransientProviderError(
                    f"OpenAI server error: {e}", status_code=status
                ) from e
            raise PermanentProviderError(
                f"OpenAI API error: {e}", status_code=status
            ) from e

        return TranscriptResult(
            text=response.strip() if isinstance(response, str) else str(response),
            confidence=1.0,  # OpenAI basic API doesn't return confidence
            words=[],  # OpenAI basic API doesn't return word timestamps
            duration_s=0.0,  # OpenAI basic API doesn't return duration
            provider=self.name,
            model=self._model,
        )

    async def supports_file(self, audio_path: str) -> bool:
        """Check if the audio file is within size limits.

        Args:
            audio_path: Path to the audio file.

        Returns:
            True if the file exists and is under 25MB.
        """
        path = Path(audio_path)
        if not path.exists():
            return False
        return path.stat().st_size <= MAX_FILE_SIZE_BYTES
