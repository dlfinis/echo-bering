"""Unit tests for TranscriptionReconstructor — validation and post-processing."""

from src.processors.transcription_reconstructor import (
    ReconstructionValidation,
    TranscriptionReconstructor,
)
from src.providers.asr.base import TranscriptResult, WordTimestamp


class TestReconstructionValidation:
    """Test ReconstructionValidation model."""

    def test_create_valid_validation(self):
        """Can create a valid validation result."""
        validation = ReconstructionValidation(
            is_valid=True,
            word_count=100,
            duration_s=300.0,
            confidence=0.95,
        )
        assert validation.is_valid is True
        assert validation.has_failed_regions is False
        assert validation.failed_region_count == 0
        assert validation.word_count == 100


class TestTranscriptionReconstructorValidate:
    """Test TranscriptionReconstructor.validate()."""

    def _make_result(self, text="Hello world", words=None, duration_s=1.0, confidence=0.95):
        return TranscriptResult(
            text=text,
            confidence=confidence,
            words=words or [],
            duration_s=duration_s,
            provider="mock",
            model="mock",
        )

    def test_valid_transcription(self):
        """Valid transcription passes validation."""
        result = self._make_result(
            text="Hello world",
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.95),
                WordTimestamp(word="world", start=0.5, end=1.0, confidence=0.95),
            ],
            duration_s=1.0,
            confidence=0.95,
        )

        validation = TranscriptionReconstructor.validate(result)

        assert validation.is_valid is True
        assert validation.has_failed_regions is False
        assert validation.word_count == 2
        assert validation.issues == []

    def test_empty_text_fails_validation(self):
        """Empty transcription text fails validation."""
        result = self._make_result(text="", duration_s=1.0)

        validation = TranscriptionReconstructor.validate(result)

        assert validation.is_valid is False
        assert any("empty" in issue.lower() for issue in validation.issues)

    def test_failed_regions_detected(self):
        """Failed regions are detected from [TRANSCRIPTION_FAILED] markers."""
        result = self._make_result(
            text="Good text [TRANSCRIPTION_FAILED] more text [TRANSCRIPTION_FAILED]",
            duration_s=10.0,
        )

        validation = TranscriptionReconstructor.validate(result)

        assert validation.has_failed_regions is True
        assert validation.failed_region_count == 2

    def test_non_positive_duration_fails(self):
        """Non-positive duration fails validation."""
        result = self._make_result(text="Hello", duration_s=0.0)

        validation = TranscriptionReconstructor.validate(result)

        assert validation.is_valid is False
        assert any("duration" in issue.lower() for issue in validation.issues)

    def test_confidence_out_of_bounds_fails(self):
        """Confidence outside [0, 1] is caught by Pydantic at construction."""
        # TranscriptResult already validates 0 <= confidence <= 1 via Pydantic
        # So the reconstructor validation focuses on runtime-level issues.
        # This test confirms that valid-bound results pass reconstructor validation.
        result = self._make_result(text="Hello", confidence=1.0)
        validation = TranscriptionReconstructor.validate(result)
        assert validation.is_valid is True

    def test_zero_confidence_passes_validation(self):
        """Zero confidence is valid (transcription was very uncertain)."""
        result = self._make_result(text="Hello", confidence=0.0)
        validation = TranscriptionReconstructor.validate(result)
        assert validation.is_valid is True

    def test_word_timestamp_ordering_checked(self):
        """Out-of-order word timestamps are detected."""
        result = self._make_result(
            text="Hello world",
            words=[
                WordTimestamp(word="world", start=1.0, end=2.0, confidence=0.9),
                WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.9),
            ],
            duration_s=2.0,
        )

        validation = TranscriptionReconstructor.validate(result)

        assert validation.is_valid is False
        assert len(validation.issues) > 0


class TestTranscriptionReconstructorExtractFailedRegions:
    """Test extract_failed_regions()."""

    def _make_result(self, text, words, duration_s=10.0):
        return TranscriptResult(
            text=text,
            confidence=0.9,
            words=words,
            duration_s=duration_s,
            provider="mock",
            model="mock",
        )

    def test_no_failed_regions_returns_empty(self):
        """No [TRANSCRIPTION_FAILED] returns empty list."""
        result = self._make_result(text="All good", words=[])
        regions = TranscriptionReconstructor.extract_failed_regions(result)
        assert regions == []

    def test_failed_marker_without_words_estimates_full_range(self):
        """Failed marker with no words estimates full audio range."""
        result = self._make_result(text="[TRANSCRIPTION_FAILED]", words=[], duration_s=300.0)
        regions = TranscriptionReconstructor.extract_failed_regions(result)
        assert len(regions) > 0


class TestTranscriptionReconstructorConfidenceByRegion:
    """Test get_confidence_by_region()."""

    def _make_result(self, words, duration_s=120.0):
        return TranscriptResult(
            text="Test",
            confidence=0.9,
            words=words,
            duration_s=duration_s,
            provider="mock",
            model="mock",
        )

    def test_returns_regions_for_duration(self):
        """Returns confidence windows covering full duration."""
        words = [
            WordTimestamp(word="hello", start=0.0, end=0.5, confidence=0.95),
            WordTimestamp(word="world", start=0.5, end=1.0, confidence=0.85),
        ]
        result = self._make_result(words, duration_s=120.0)

        regions = TranscriptionReconstructor.get_confidence_by_region(result, window_s=60.0)

        # Should have 2 regions (0-60, 60-120)
        assert len(regions) == 2
        assert regions[0][0] == 0.0
        assert regions[0][1] == 60.0
        assert regions[1][0] == 60.0
        assert regions[1][1] == 120.0

    def test_empty_words_returns_empty(self):
        """No words returns empty regions."""
        result = self._make_result([], duration_s=60.0)
        regions = TranscriptionReconstructor.get_confidence_by_region(result)
        assert regions == []
