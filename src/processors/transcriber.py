"""Transcription orchestrator with adaptive chunking.

Attempts full audio transcription first, falls back to chunked
transcription when providers reject oversized files.
"""

import asyncio
import json
from pathlib import Path
from typing import List, Optional

from src.processors.chunking import (
    ChunkMetadata,
    ChunkingStrategy,
    FullAudioStrategy,
    TimedChunkingStrategy,
)
from src.providers.asr.base import ASRProvider, TranscriptResult
from src.utils.cost_estimator import CostEstimator
from src.utils.errors import PermanentProviderError, ProviderError, TransientProviderError
from src.utils.logger import get_logger
from src.utils.retry import RetryPolicy

logger = get_logger(__name__)

# Keywords that indicate a provider rejected the file due to duration/size limits
DURATION_REJECTION_KEYWORDS = [
    "duration exceeded",
    "duration exceeds", 
    "file too large",
    "audio duration",
    "maximum duration",
    "max duration",
    "too long",
    "request_too_large",
    "request entity too large",
    "entity too large",
    "exceeds limit",
    "exceeds maximum",
]


def is_duration_rejection(error: ProviderError) -> bool:
    """Check if a provider error indicates file duration/size rejection.

    Args:
        error: The provider error to check.

    Returns:
        True if the error indicates a duration/size rejection.
    """
    message = error.message.lower()
    return any(keyword in message for keyword in DURATION_REJECTION_KEYWORDS)


class Transcriber:
    """Orchestrate ASR transcription with adaptive chunking.

    Strategy:
    1. Try full audio transcription first.
    2. If provider rejects due to duration/size, fall back to chunking.
    3. Transcribe each chunk, reassemble with overlap resolution.
    """

    def __init__(
        self,
        asr_provider: ASRProvider,
        chunking_strategy: Optional[ChunkingStrategy] = None,
        output_dir: Optional[Path] = None,
        cost_estimator: Optional[CostEstimator] = None,
        max_retries: int = 2,
    ):
        """Initialize Transcriber.

        Args:
            asr_provider: ASR provider implementation.
            chunking_strategy: Strategy for chunking. Defaults to FullAudioStrategy.
            output_dir: Output directory for checkpoints.
            cost_estimator: Cost tracker for transcription attempts.
            max_retries: Maximum retries for transient errors.
        """
        self.asr_provider = asr_provider
        self.chunking_strategy = chunking_strategy or FullAudioStrategy()
        self.output_dir = output_dir or Path("./output")
        self.cost_estimator = cost_estimator or CostEstimator()
        self.max_retries = max_retries
        self.retry_policy = RetryPolicy(max_retries=max_retries)

    async def transcribe(self, audio_path: Path) -> TranscriptResult:
        """Transcribe audio with adaptive chunking.

        First attempts full audio transcription. If the provider rejects
        the file due to duration/size limits, falls back to chunked
        transcription.

        Args:
            audio_path: Path to the audio file.

        Returns:
            TranscriptResult with the full transcription.

        Raises:
            ProviderError: If transcription fails after all retries.
        """
        # Check for existing checkpoint
        checkpoint_path = self.output_dir / ".checkpoint" / "asr" / "raw_transcript.json"
        if checkpoint_path.exists():
            logger.info("Loading ASR checkpoint: %s", checkpoint_path)
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            return TranscriptResult(**data)

        # Get audio duration for cost estimation
        duration_s = self._get_audio_duration(audio_path)

        # Try full audio first
        try:
            result = await self._transcribe_with_retry(audio_path)
            logger.info("Full audio transcription succeeded")
            self._save_checkpoint(result)
            return result
        except ProviderError as e:
            if is_duration_rejection(e):
                logger.info("Full audio rejected by provider — falling back to chunking")
                return await self._transcribe_chunks(audio_path, duration_s)
            # Not a duration rejection — re-raise
            raise

    async def _transcribe_with_retry(self, audio_path: Path) -> TranscriptResult:
        """Transcribe with retry logic for transient errors.

        Args:
            audio_path: Path to the audio file.

        Returns:
            TranscriptResult from successful transcription.

        Raises:
            ProviderError: If transcription fails after all retries.
        """
        errors: List[str] = []

        for attempt in range(self.max_retries + 1):
            try:
                result = await self.asr_provider.transcribe(str(audio_path))
                # Track cost
                cost = self.cost_estimator.estimate_asr_cost(
                    result.duration_s, result.provider
                )
                self.cost_estimator.add_cost(cost)
                return result
            except PermanentProviderError:
                raise
            except TransientProviderError as e:
                errors.append(str(e))
                if attempt < self.max_retries:
                    delay = 2 ** attempt  # Exponential backoff: 1s, 2s
                    logger.warning(
                        "Transient error (attempt %d/%d): %s — retrying in %ds",
                        attempt + 1,
                        self.max_retries + 1,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("All retries exhausted for transcription")

        raise ProviderError(
            f"Transcription failed after {self.max_retries + 1} attempts: {'; '.join(errors)}"
        )

    async def _transcribe_chunks(
        self, audio_path: Path, duration_s: float
    ) -> TranscriptResult:
        """Transcribe audio using chunked strategy.

        Args:
            audio_path: Path to the audio file.
            duration_s: Total audio duration in seconds.

        Returns:
            Merged TranscriptResult from all chunks.
        """
        # Switch to timed chunking if currently using full audio strategy
        strategy = self.chunking_strategy
        if isinstance(strategy, FullAudioStrategy):
            strategy = TimedChunkingStrategy()

        # Create chunks
        chunk_meta = strategy.create_chunks(audio_path, duration_s)
        logger.info("Created %d chunks for transcription", len(chunk_meta))

        # Transcribe each chunk
        results: List[Optional[TranscriptResult]] = []
        for meta in chunk_meta:
            try:
                result = await self._transcribe_with_retry(meta.chunk_path)
                results.append(result)
            except ProviderError as e:
                logger.error("Chunk %d transcription failed: %s", meta.chunk_index, e)
                results.append(None)

        # Reassemble with overlap resolution
        merged = strategy.reassemble(results, chunk_meta)
        logger.info("Chunk transcription reassembled: %.1fs, confidence=%.2f",
                    merged.duration_s, merged.confidence)

        self._save_checkpoint(merged)
        return merged

    def _save_checkpoint(self, result: TranscriptResult) -> None:
        """Save transcription result to checkpoint.

        Args:
            result: The transcript result to save.
        """
        checkpoint_dir = self.output_dir / ".checkpoint" / "asr"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = checkpoint_dir / "raw_transcript.json"

        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2)

        logger.info("ASR checkpoint saved: %s", checkpoint_path)

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration using ffprobe.

        Args:
            audio_path: Path to the audio file.

        Returns:
            Duration in seconds, or 0.0 if unable to determine.
        """
        import subprocess

        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError) as e:
            logger.debug("Could not determine audio duration: %s", e)

        return 0.0
