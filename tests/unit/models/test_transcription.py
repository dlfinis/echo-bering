"""Unit tests for transcription domain models."""

from src.models.transcription import TranscriptionAttempt, TranscriptionSummary
from src.providers.asr.base import TranscriptResult, WordTimestamp


class TestTranscriptionAttempt:
    """Test TranscriptionAttempt model."""

    def test_create_attempt(self):
        """Can create a transcription attempt."""
        attempt = TranscriptionAttempt(
            attempt_number=1,
            provider="groq",
            strategy="full",
            cost_usd=0.001,
            success=True,
        )
        assert attempt.attempt_number == 1
        assert attempt.provider == "groq"
        assert attempt.strategy == "full"
        assert attempt.success is True
        assert attempt.chunk_index is None
        assert attempt.error_message is None

    def test_create_failed_attempt(self):
        """Can create a failed attempt with error message."""
        attempt = TranscriptionAttempt(
            attempt_number=2,
            provider="groq",
            strategy="chunk",
            chunk_index=1,
            cost_usd=0.0,
            success=False,
            error_message="duration exceeded",
        )
        assert attempt.success is False
        assert attempt.chunk_index == 1
        assert attempt.error_message == "duration exceeded"


class TestTranscriptionSummary:
    """Test TranscriptionSummary model."""

    def _make_result(self):
        return TranscriptResult(
            text="Hello world",
            confidence=0.95,
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.95),
            ],
            duration_s=1.0,
            provider="mock",
            model="mock",
        )

    def test_create_summary(self):
        """Can create a transcription summary."""
        result = self._make_result()
        summary = TranscriptionSummary(
            result=result,
            total_cost_usd=0.001,
            used_chunking=False,
        )
        assert summary.result.text == "Hello world"
        assert summary.total_cost_usd == 0.001
        assert summary.used_chunking is False
        assert summary.chunk_count == 0
        assert summary.failed_chunks == 0
        assert summary.attempts == []

    def test_summary_with_attempts(self):
        """Summary tracks multiple attempts."""
        result = self._make_result()
        summary = TranscriptionSummary(
            result=result,
            attempts=[
                TranscriptionAttempt(
                    attempt_number=1,
                    provider="groq",
                    strategy="full",
                    cost_usd=0.001,
                    success=False,
                    error_message="duration exceeded",
                ),
                TranscriptionAttempt(
                    attempt_number=2,
                    provider="groq",
                    strategy="chunk",
                    chunk_index=0,
                    cost_usd=0.0005,
                    success=True,
                ),
            ],
            total_cost_usd=0.0015,
            used_chunking=True,
            chunk_count=2,
        )
        assert len(summary.attempts) == 2
        assert summary.used_chunking is True
        assert summary.chunk_count == 2

    def test_summary_with_failed_chunks(self):
        """Summary tracks failed chunk count."""
        result = self._make_result()
        summary = TranscriptionSummary(
            result=result,
            used_chunking=True,
            chunk_count=4,
            failed_chunks=1,
            total_cost_usd=0.002,
        )
        assert summary.failed_chunks == 1
        assert summary.chunk_count == 4
