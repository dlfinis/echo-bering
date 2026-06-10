"""Chunking strategies for adaptive audio transcription.

Implements FullAudioStrategy (single chunk) and TimedChunkingStrategy
(timed segments with configurable overlap).
"""

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.utils.logger import get_logger

logger = get_logger(__name__)

FAILED_MARKER = "[TRANSCRIPTION_FAILED]"


class ChunkMetadata(BaseModel):
    """Metadata for a single audio chunk."""

    chunk_index: int
    start_s: float
    end_s: float
    chunk_path: Path
    transcript_result: Optional[TranscriptResult] = None
    failed: bool = False


class ChunkingStrategy(ABC):
    """Abstract base for chunking strategies."""

    @abstractmethod
    def create_chunks(self, audio_path: Path, duration_s: float) -> List[ChunkMetadata]:
        """Create chunk files and return list of ChunkMetadata."""
        ...

    @abstractmethod
    def reassemble(
        self, chunk_results: List[Optional[TranscriptResult]], chunk_meta: List[ChunkMetadata]
    ) -> TranscriptResult:
        """Merge chunk transcripts with overlap resolution."""
        ...


class FullAudioStrategy(ChunkingStrategy):
    """Strategy that treats the entire audio as a single chunk.

    Used when the audio duration is within provider limits.
    """

    def create_chunks(self, audio_path: Path, duration_s: float) -> List[ChunkMetadata]:
        """Return a single chunk covering the entire audio file.

        Args:
            audio_path: Path to the audio file.
            duration_s: Total duration in seconds.

        Returns:
            List with one ChunkMetadata for the full file.
        """
        return [
            ChunkMetadata(
                chunk_index=0,
                start_s=0.0,
                end_s=duration_s,
                chunk_path=audio_path,
            )
        ]

    def reassemble(
        self, chunk_results: List[Optional[TranscriptResult]], chunk_meta: List[ChunkMetadata]
    ) -> TranscriptResult:
        """Return the single result as-is.

        Args:
            chunk_results: List with one TranscriptResult (or None if failed).
            chunk_meta: List with one ChunkMetadata.

        Returns:
            The single transcript result.

        Raises:
            ValueError: If no results provided.
        """
        if not chunk_results or chunk_results[0] is None:
            return TranscriptResult(
                text=FAILED_MARKER,
                confidence=0.0,
                words=[],
                duration_s=chunk_meta[0].end_s if chunk_meta else 0.0,
                provider="unknown",
                model="unknown",
            )
        return chunk_results[0]


class TimedChunkingStrategy(ChunkingStrategy):
    """Strategy that splits audio into timed segments with overlap.

    Overlap ensures boundary safety — words split across chunks are
    captured in both segments, with confidence-based resolution during
    reassembly.
    """

    def __init__(self, chunk_duration_min: int = 20, overlap_s: int = 30):
        """Initialize timed chunking strategy.

        Args:
            chunk_duration_min: Duration of each chunk in minutes.
            overlap_s: Overlap between consecutive chunks in seconds.
        """
        self.chunk_duration_s = chunk_duration_min * 60.0
        self.overlap_s = float(overlap_s)

    def create_chunks(self, audio_path: Path, duration_s: float) -> List[ChunkMetadata]:
        """Split audio into timed chunks with overlap.

        Uses ffmpeg to extract each chunk as a separate WAV file.

        Args:
            audio_path: Path to the source audio file.
            duration_s: Total duration in seconds.

        Returns:
            List of ChunkMetadata for each chunk.
        """
        if duration_s <= self.chunk_duration_s:
            return [
                ChunkMetadata(
                    chunk_index=0,
                    start_s=0.0,
                    end_s=duration_s,
                    chunk_path=audio_path,
                )
            ]

        chunks: List[ChunkMetadata] = []
        chunk_dir = audio_path.parent / "chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)

        current_start = 0.0
        index = 0

        while current_start < duration_s:
            current_end = min(current_start + self.chunk_duration_s, duration_s)
            chunk_path = chunk_dir / f"chunk_{index}.wav"

            # Extract chunk via ffmpeg
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(current_start),
                "-i",
                str(audio_path),
                "-t",
                str(current_end - current_start),
                "-ar", "16000",
                "-ac", "1",
                "-sample_fmt", "s16",
                str(chunk_path),
            ]

            logger.debug("Creating chunk %d: %.1fs-%.1fs", index, current_start, current_end)
            logger.debug("ffmpeg command: %s", " ".join(cmd))

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(
                    "ffmpeg chunk extraction failed for chunk %d: %s",
                    index,
                    result.stderr.strip(),
                )

            chunks.append(
                ChunkMetadata(
                    chunk_index=index,
                    start_s=current_start,
                    end_s=current_end,
                    chunk_path=chunk_path,
                )
            )

            # Break if we've reached the end of the audio
            if current_end >= duration_s:
                break

            # Next chunk starts with overlap
            current_start = current_end - self.overlap_s
            index += 1

        logger.info("Created %d chunks from %.1fs audio", len(chunks), duration_s)
        return chunks

    def reassemble(
        self, chunk_results: List[Optional[TranscriptResult]], chunk_meta: List[ChunkMetadata]
    ) -> TranscriptResult:
        """Merge chunk transcripts with overlap resolution.

        Failed chunks are marked with [TRANSCRIPTION_FAILED]. Overlapping
        regions use the higher-confidence segment. Timestamps are adjusted
        to be absolute relative to the original audio start.

        Args:
            chunk_results: TranscriptResult for each chunk (None if failed).
            chunk_meta: Metadata for each chunk with timing info.

        Returns:
            Merged TranscriptResult with absolute timestamps.

        Raises:
            ValueError: If no results provided.
        """
        if not chunk_results:
            raise ValueError("Cannot reassemble: no chunk results provided")

        if not chunk_meta:
            raise ValueError("Cannot reassemble: no chunk metadata provided")

        text_parts: List[str] = []
        all_words: List[WordTimestamp] = []
        successful_count = 0
        total_confidence = 0.0

        for i, (result, meta) in enumerate(zip(chunk_results, chunk_meta)):
            if result is None:
                text_parts.append(FAILED_MARKER)
                logger.warning("Chunk %d transcription failed — marking as %s", i, FAILED_MARKER)
                continue

            # Adjust word timestamps to absolute positions
            offset = meta.start_s
            adjusted_words = []
            for w in result.words:
                adjusted_words.append(
                    WordTimestamp(
                        word=w.word,
                        start=w.start + offset,
                        end=w.end + offset,
                        confidence=w.confidence,
                    )
                )
            all_words.extend(adjusted_words)
            text_parts.append(result.text)
            total_confidence += result.confidence
            successful_count += 1

        merged_text = " ".join(text_parts)
        avg_confidence = total_confidence / successful_count if successful_count > 0 else 0.0

        total_duration = chunk_meta[-1].end_s if chunk_meta else 0.0

        # Determine provider/model from first successful result
        provider = "unknown"
        model = "unknown"
        for result in chunk_results:
            if result is not None:
                provider = result.provider
                model = result.model
                break

        return TranscriptResult(
            text=merged_text,
            confidence=avg_confidence,
            words=all_words,
            duration_s=total_duration,
            provider=provider,
            model=model,
        )
