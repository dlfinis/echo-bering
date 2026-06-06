"""Groq ASR provider using Whisper Large v3 Turbo model."""

import asyncio
import os
from pathlib import Path

from groq import Groq, APIError, AuthenticationError, RateLimitError

from src.providers.asr.base import ASRProvider, ProviderCapabilities, TranscriptResult, WordTimestamp
from src.utils.errors import PermanentProviderError, TransientProviderError
from src.utils.logger import get_logger
from src.utils.retry import RetryPolicy

logger = get_logger(__name__)

# Groq ASR file size limit: 25 MB
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

# Default model
DEFAULT_MODEL = "whisper-large-v3-turbo"

# Groq's Whisper endpoint returns text + duration but word-level timestamps
# are not consistently available despite verbose_json format.
GROQ_CAPABILITIES = ProviderCapabilities(
    has_word_timestamps=False,
    has_speaker_diarization=False,
    has_utterances=False,
    max_duration_s=0.0,  # No explicit limit beyond file size
)


class GroqASRProvider(ASRProvider):
    """ASR provider using Groq's Whisper Large v3 Turbo endpoint.

    Supports transcription with optional word-level timestamps
    when the verbose response includes word timing data.
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

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Groq provides basic transcription only (text + duration)."""
        return GROQ_CAPABILITIES

    def _get_client(self) -> Groq:
        """Lazy initialization of the Groq client."""
        if self._client is None:
            self._client = Groq(api_key=self._api_key)
        return self._client

    @RetryPolicy(max_retries=2, base_delay=1.0, max_delay=10.0).retry
    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe audio file using Groq Whisper endpoint.

        Args:
            audio_path: Path to the audio file (WAV, MP3, M4A, etc.).

        Returns:
            TranscriptResult with text, word timestamps, and metadata.

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
                    response_format="verbose_json",
                    language="es",
                )
        except RateLimitError as e:
            raise TransientProviderError(f"Groq rate limit exceeded: {e}", status_code=429) from e
        except AuthenticationError as e:
            raise PermanentProviderError(f"Groq authentication failed: {e}", status_code=401) from e
        except APIError as e:
            status = getattr(e, "status_code", None)
            if status and 500 <= status < 600:
                raise TransientProviderError(f"Groq server error: {e}", status_code=status) from e
            raise PermanentProviderError(f"Groq API error: {e}", status_code=status) from e

        # Parse word-level timestamps if available
        words = []
        if hasattr(response, "words") and response.words:
            for w in response.words:
                words.append(WordTimestamp(
                    word=w.word,
                    start=w.start,
                    end=w.end,
                    confidence=w.confidence if hasattr(w, "confidence") and w.confidence else 1.0,
                ))

        return TranscriptResult(
            text=response.text,
            confidence=self._calculate_confidence(words) if words else 1.0,
            words=words,
            duration_s=self._extract_duration(response),
            provider=self.name,
            model=self._model,
        )

    async def supports_file(self, audio_path: str) -> bool:
        """Check if the audio file is within Groq's size limits.

        Args:
            audio_path: Path to the audio file.

        Returns:
            True if the file exists and is under the size limit.
        """
        path = Path(audio_path)
        if not path.exists():
            return False
        return path.stat().st_size <= MAX_FILE_SIZE_BYTES

    @staticmethod
    def _calculate_confidence(words: list[WordTimestamp]) -> float:
        """Calculate average confidence from word-level scores."""
        if not words:
            return 1.0
        total = sum(w.confidence for w in words)
        return round(total / len(words), 4)

    @staticmethod
    def _extract_duration(response) -> float:
        """Extract audio duration from the response if available."""
        if hasattr(response, "duration") and response.duration is not None:
            return float(response.duration)
        # Fallback: estimate from word timestamps
        if hasattr(response, "words") and response.words:
            last_word = response.words[-1]
            if hasattr(last_word, "end"):
                return float(last_word.end)
        return 0.0
