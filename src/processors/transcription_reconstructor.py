"""Transcription reconstruction — validates and post-processes merged transcripts."""

from typing import List, Tuple

from pydantic import BaseModel, Field

from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.utils.logger import get_logger

logger = get_logger(__name__)

FAILED_MARKER = "[TRANSCRIPTION_FAILED]"


class ReconstructionValidation(BaseModel):
    """Validation result for a reconstructed transcription."""

    is_valid: bool
    has_failed_regions: bool = False
    failed_region_count: int = 0
    word_count: int = 0
    duration_s: float = 0.0
    confidence: float = 0.0
    issues: List[str] = Field(default_factory=list)


class TranscriptionReconstructor:
    """Validate and post-process reconstructed transcriptions.

    Provides validation, integrity checks, and utility methods for
    working with merged transcription results from chunked processing.
    """

    @staticmethod
    def validate(result: TranscriptResult) -> ReconstructionValidation:
        """Validate a reconstructed transcription for integrity.

        Checks:
        - Text is non-empty
        - Word timestamps are in order and non-overlapping
        - Duration is positive
        - Confidence is within bounds

        Args:
            result: The transcript result to validate.

        Returns:
            ReconstructionValidation with validation status and details.
        """
        issues: List[str] = []
        has_failed_regions = FAILED_MARKER in result.text
        failed_region_count = result.text.count(FAILED_MARKER)

        # Check text is non-empty (beyond just failed markers)
        clean_text = result.text.replace(FAILED_MARKER, "").strip()
        if not clean_text and not has_failed_regions:
            issues.append("Transcription text is empty")

        # Check duration
        if result.duration_s <= 0:
            issues.append(f"Duration is non-positive: {result.duration_s}")

        # Check confidence bounds
        if result.confidence < 0 or result.confidence > 1:
            issues.append(f"Confidence out of bounds: {result.confidence}")

        # Check word timestamp ordering
        if result.words:
            ordering_issues = TranscriptionReconstructor._check_word_ordering(result.words)
            issues.extend(ordering_issues)

        word_count = len(result.words)

        is_valid = len(issues) == 0

        return ReconstructionValidation(
            is_valid=is_valid,
            has_failed_regions=has_failed_regions,
            failed_region_count=failed_region_count,
            word_count=word_count,
            duration_s=result.duration_s,
            confidence=result.confidence,
            issues=issues,
        )

    @staticmethod
    def _check_word_ordering(words: List[WordTimestamp]) -> List[str]:
        """Check that word timestamps are in chronological order.

        Args:
            words: List of word timestamps.

        Returns:
            List of issue descriptions, empty if all valid.
        """
        issues: List[str] = []
        for i in range(1, len(words)):
            if words[i].start < words[i - 1].end:
                issues.append(
                    f"Word '{words[i].word}' at {words[i].start}s starts before "
                    f"'{words[i-1].word}' ends at {words[i-1].end}s"
                )
        return issues

    @staticmethod
    def extract_failed_regions(result: TranscriptResult) -> List[Tuple[float, float]]:
        """Identify time regions where transcription failed.

        This is a best-effort estimation based on word timestamps around
        [TRANSCRIPTION_FAILED] markers.

        Args:
            result: The transcript result to analyze.

        Returns:
            List of (start_s, end_s) tuples for failed regions.
        """
        if FAILED_MARKER not in result.text:
            return []

        regions: List[Tuple[float, float]] = []

        # Find words before and after each failed marker
        # This is approximate — in practice, chunk metadata would provide exact boundaries
        words = result.words
        if not words:
            return [(0.0, result.duration_s)]

        # Estimate: failed regions are gaps between word sequences
        # A proper implementation would track chunk boundaries during reconstruction
        gap_threshold = 5.0  # seconds
        for i in range(1, len(words)):
            gap = words[i].start - words[i - 1].end
            if gap > gap_threshold:
                regions.append((words[i - 1].end, words[i].start))

        return regions

    @staticmethod
    def get_confidence_by_region(
        result: TranscriptResult, window_s: float = 60.0
    ) -> List[Tuple[float, float, float]]:
        """Get average confidence for time windows.

        Args:
            result: The transcript result.
            window_s: Window size in seconds.

        Returns:
            List of (start_s, end_s, avg_confidence) tuples.
        """
        if not result.words or result.duration_s <= 0:
            return []

        regions: List[Tuple[float, float, float]] = []
        current_start = 0.0

        while current_start < result.duration_s:
            current_end = min(current_start + window_s, result.duration_s)

            # Find words in this window
            window_words = [
                w for w in result.words
                if w.start >= current_start and w.end <= current_end
            ]

            if window_words:
                avg_conf = sum(w.confidence for w in window_words) / len(window_words)
            else:
                avg_conf = 0.0

            regions.append((current_start, current_end, avg_conf))
            current_start = current_end

        return regions
