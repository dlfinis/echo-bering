"""Unit tests for Transcriber — adaptive transcription orchestration."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.processors.chunking import ChunkMetadata, FullAudioStrategy, TimedChunkingStrategy
from src.processors.transcriber import Transcriber, is_duration_rejection
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.utils.errors import PermanentProviderError, ProviderError, TransientProviderError


class TestIsDurationRejection:
    """Test provider rejection detection."""

    def test_groq_duration_exceeded(self):
        """Detects Groq duration exceeded error."""
        error = ProviderError("duration exceeded: max 25 minutes")
        assert is_duration_rejection(error) is True

    def test_openai_file_too_large(self):
        """Detects OpenAI file too large error."""
        error = ProviderError("File too large")
        assert is_duration_rejection(error) is True

    def test_assemblyai_duration_limit(self):
        """Detects AssemblyAI duration limit error."""
        error = ProviderError("audio duration exceeds limit")
        assert is_duration_rejection(error) is True

    def test_generic_error_not_rejection(self):
        """Generic errors are not treated as duration rejections."""
        error = ProviderError("Connection refused")
        assert is_duration_rejection(error) is False

    def test_transient_error_not_rejection(self):
        """Transient errors are not duration rejections."""
        error = TransientProviderError("Rate limited", status_code=429)
        assert is_duration_rejection(error) is False


class TestTranscriberFullAudio:
    """Test Transcriber with full audio strategy."""

    def _make_transcriber(self, mock_asr, output_dir=None):
        return Transcriber(
            asr_provider=mock_asr,
            chunking_strategy=FullAudioStrategy(),
            output_dir=output_dir or Path("/tmp/output"),
            cost_estimator=MagicMock(),
        )

    def _make_result(self, text="Hello world"):
        return TranscriptResult(
            text=text,
            confidence=0.95,
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.95),
                WordTimestamp(word="world", start=0.5, end=1.0, confidence=0.95),
            ],
            duration_s=1.0,
            provider="mock",
            model="mock-model",
        )

    @pytest.mark.asyncio
    async def test_full_audio_success_single_call(self, tmp_path):
        """Full audio success calls transcribe once."""
        mock_asr = MagicMock()
        mock_asr.transcribe = AsyncMock(return_value=self._make_result())
        mock_asr.supports_file = AsyncMock(return_value=True)

        transcriber = self._make_transcriber(mock_asr, output_dir=tmp_path)
        result = await transcriber.transcribe(Path("/tmp/audio.wav"))

        assert result.text == "Hello world"
        assert result.confidence == 0.95
        mock_asr.transcribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_checkpoint_saved_after_completion(self, tmp_path):
        """Checkpoint saved after successful transcription."""
        mock_asr = MagicMock()
        mock_asr.transcribe = AsyncMock(return_value=self._make_result())
        mock_asr.supports_file = AsyncMock(return_value=True)

        transcriber = self._make_transcriber(mock_asr, output_dir=tmp_path)
        await transcriber.transcribe(Path("/tmp/audio.wav"))

        checkpoint_path = tmp_path / ".checkpoint" / "asr" / "raw_transcript.json"
        assert checkpoint_path.exists()
        data = json.loads(checkpoint_path.read_text())
        assert data["text"] == "Hello world"


class TestTranscriberFallbackToChunking:
    """Test Transcriber fallback to chunking when full audio rejected."""

    def _make_result(self, text="Hello world", confidence=0.95):
        return TranscriptResult(
            text=text,
            confidence=confidence,
            words=[],
            duration_s=300.0,
            provider="mock",
            model="mock-model",
        )

    def _make_transcriber(self, mock_asr, chunking_strategy=None, output_dir=None):
        return Transcriber(
            asr_provider=mock_asr,
            chunking_strategy=chunking_strategy or TimedChunkingStrategy(chunk_duration_min=5, overlap_s=10),
            output_dir=output_dir or Path("/tmp/output"),
            cost_estimator=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_full_audio_rejected_triggers_chunking(self, tmp_path):
        """Full audio rejection triggers chunking fallback."""
        mock_asr = MagicMock()
        call_count = 0

        async def mock_transcribe(audio_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProviderError("duration exceeded: max 25 minutes")
            return self._make_result(text=f"Chunk {call_count - 1} text")

        mock_asr.transcribe = mock_transcribe
        mock_asr.supports_file = AsyncMock(return_value=False)

        transcriber = self._make_transcriber(mock_asr, output_dir=tmp_path)

        # Patch create_chunks to return predictable chunks
        with patch.object(TimedChunkingStrategy, "create_chunks") as mock_create:
            mock_create.return_value = [
                ChunkMetadata(chunk_index=0, start_s=0.0, end_s=300.0, chunk_path=Path("chunk_0.wav")),
                ChunkMetadata(chunk_index=1, start_s=290.0, end_s=600.0, chunk_path=Path("chunk_1.wav")),
            ]
            result = await transcriber.transcribe(Path("/tmp/audio.wav"))

        assert "Chunk" in result.text
        # Transcribe was called more than once (full + chunks)
        assert call_count > 1

    @pytest.mark.asyncio
    async def test_chunk_partial_failure_marked(self, tmp_path):
        """Partial chunk failure handled with [TRANSCRIPTION_FAILED]."""
        mock_asr = MagicMock()
        call_count = 0

        async def mock_transcribe(audio_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProviderError("duration exceeded")
            if call_count <= 4:  # Chunk 1: fail all 3 retries (calls 2, 3, 4)
                raise TransientProviderError("Chunk 1 failed", status_code=500)
            return self._make_result(text=f"Chunk {call_count - 4} text")

        mock_asr.transcribe = mock_transcribe
        mock_asr.supports_file = AsyncMock(return_value=False)

        transcriber = self._make_transcriber(mock_asr, output_dir=tmp_path)

        with patch.object(TimedChunkingStrategy, "create_chunks") as mock_create:
            mock_create.return_value = [
                ChunkMetadata(chunk_index=0, start_s=0.0, end_s=300.0, chunk_path=Path("chunk_0.wav")),
                ChunkMetadata(chunk_index=1, start_s=290.0, end_s=600.0, chunk_path=Path("chunk_1.wav")),
            ]
            result = await transcriber.transcribe(Path("/tmp/audio.wav"))

        assert "[TRANSCRIPTION_FAILED]" in result.text

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_transient_error(self, tmp_path):
        """Retry succeeds on transient error."""
        mock_asr = MagicMock()
        call_count = 0

        async def mock_transcribe(audio_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TransientProviderError("Rate limited", status_code=429)
            return self._make_result()

        mock_asr.transcribe = mock_transcribe
        mock_asr.supports_file = AsyncMock(return_value=True)

        transcriber = self._make_transcriber(mock_asr, chunking_strategy=FullAudioStrategy(), output_dir=tmp_path)
        result = await transcriber.transcribe(Path("/tmp/audio.wav"))

        assert result.text == "Hello world"
        assert call_count == 2  # Initial failure + retry success

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises(self, tmp_path):
        """All retries exhausted raises ProviderError."""
        mock_asr = MagicMock()
        call_count = 0

        async def mock_transcribe(audio_path):
            nonlocal call_count
            call_count += 1
            raise TransientProviderError("Always fails", status_code=503)

        mock_asr.transcribe = mock_transcribe
        mock_asr.supports_file = AsyncMock(return_value=True)

        transcriber = self._make_transcriber(mock_asr, chunking_strategy=FullAudioStrategy(), output_dir=tmp_path)

        with pytest.raises(ProviderError):
            await transcriber.transcribe(Path("/tmp/audio.wav"))

        # Original + 2 retries = 3 calls
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_error_not_retried(self, tmp_path):
        """Permanent error raises immediately without retry."""
        mock_asr = MagicMock()
        call_count = 0

        async def mock_transcribe(audio_path):
            nonlocal call_count
            call_count += 1
            raise PermanentProviderError("Invalid API key", status_code=401)

        mock_asr.transcribe = mock_transcribe
        mock_asr.supports_file = AsyncMock(return_value=True)

        transcriber = self._make_transcriber(mock_asr, chunking_strategy=FullAudioStrategy(), output_dir=tmp_path)

        with pytest.raises(PermanentProviderError):
            await transcriber.transcribe(Path("/tmp/audio.wav"))

        assert call_count == 1  # No retries for permanent errors
