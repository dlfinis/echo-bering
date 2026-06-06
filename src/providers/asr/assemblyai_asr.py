"""AssemblyAI ASR provider for audio transcription."""

import os
from pathlib import Path

import assemblyai as aai

from src.providers.asr.base import ASRProvider, TranscriptResult, WordTimestamp
from src.utils.errors import PermanentProviderError, TransientProviderError
from src.utils.logger import get_logger
from src.utils.retry import RetryPolicy

logger = get_logger(__name__)

# Default model identifier
DEFAULT_MODEL = "assemblyai-default"


class AssemblyAIASRProvider(ASRProvider):
    """ASR provider using AssemblyAI's transcription API.

    Provides basic transcription without Auto Chapters.
    Supports word-level timestamps when available.
    """

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("ASSEMBLYAI_API_KEY")
        if not self._api_key:
            raise PermanentProviderError(
                "AssemblyAI API key not provided. Set ASSEMBLYAI_API_KEY environment variable "
                "or pass api_key to the constructor."
            )
        self._model = model
        self._transcriber: aai.Transcriber | None = None

    @property
    def name(self) -> str:
        return "assemblyai"

    @property
    def model(self) -> str:
        return self._model

    def _get_transcriber(self) -> aai.Transcriber:
        """Lazy initialization of the AssemblyAI transcriber."""
        if self._transcriber is None:
            aai.settings.api_key = self._api_key
            self._transcriber = aai.Transcriber()
        return self._transcriber

    @RetryPolicy(max_retries=2, base_delay=1.0, max_delay=10.0).retry
    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe audio file using AssemblyAI.

        Args:
            audio_path: Path to the audio file.

        Returns:
            TranscriptResult with text, word timestamps, and metadata.

        Raises:
            TransientProviderError: Service errors (retryable).
            PermanentProviderError: Auth errors or missing files (not retryable).
        """
        path = Path(audio_path)
        if not path.exists():
            raise PermanentProviderError(f"Audio file not found: {audio_path}")

        transcriber = self._get_transcriber()

        try:
            transcript = transcriber.transcribe(
                str(path),
                config=aai.TranscriptionConfig(
                    punctuate=True,
                    format_text=True,
                ),
            )
        except aai.AssemblyAIError as e:
            status = getattr(e, "status_code", None)
            if status and 500 <= status < 600:
                raise TransientProviderError(
                    f"AssemblyAI service error: {e}", status_code=status
                ) from e
            if status == 401:
                raise PermanentProviderError(
                    f"AssemblyAI authentication failed: {e}", status_code=status
                ) from e
            raise PermanentProviderError(
                f"AssemblyAI API error: {e}", status_code=status
            ) from e

        # Parse word-level timestamps if available
        words = []
        if transcript.words:
            for w in transcript.words:
                words.append(WordTimestamp(
                    word=w.text,
                    start=w.start / 1000.0,  # AssemblyAI returns milliseconds
                    end=w.end / 1000.0,
                    confidence=w.confidence if w.confidence else 1.0,
                ))

        # Duration in seconds (AssemblyAI returns milliseconds)
        duration_s = transcript.audio_duration / 1000.0 if transcript.audio_duration else 0.0

        return TranscriptResult(
            text=transcript.text or "",
            confidence=transcript.confidence if transcript.confidence else 1.0,
            words=words,
            duration_s=duration_s,
            provider=self.name,
            model=self._model,
        )

    async def supports_file(self, audio_path: str) -> bool:
        """Check if the audio file exists and is accessible.

        AssemblyAI supports a wide range of formats and sizes.

        Args:
            audio_path: Path to the audio file.

        Returns:
            True if the file exists.
        """
        path = Path(audio_path)
        return path.exists()
