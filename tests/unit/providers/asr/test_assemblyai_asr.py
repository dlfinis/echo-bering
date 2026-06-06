"""Tests for AssemblyAIASRProvider implementation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.providers.asr.assemblyai_asr import AssemblyAIASRProvider
from src.providers.asr.base import TranscriptResult
from src.utils.errors import PermanentProviderError, TransientProviderError


class TestAssemblyAIASRProvider:
    """Test AssemblyAIASRProvider with mocked AssemblyAI client."""

    @pytest.fixture
    def provider(self):
        """Create AssemblyAIASRProvider with test API key."""
        os.environ["ASSEMBLYAI_API_KEY"] = "test-assemblyai-api-key"
        return AssemblyAIASRProvider(api_key="test-assemblyai-api-key")

    def test_provider_name_and_model(self, provider):
        """Provider identifies itself correctly."""
        assert provider.name == "assemblyai"
        assert provider.model == "assemblyai-default"

    def test_provider_custom_model(self):
        """Provider accepts a custom model name."""
        os.environ["ASSEMBLYAI_API_KEY"] = "test-assemblyai-api-key"
        provider = AssemblyAIASRProvider(api_key="test-assemblyai-api-key", model="nano")
        assert provider.model == "nano"

    def test_missing_api_key_raises(self):
        """Missing API key raises PermanentProviderError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(PermanentProviderError) as exc_info:
                AssemblyAIASRProvider()
            assert "ASSEMBLYAI_API_KEY" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transcribe_returns_transcript_result(self, provider, tmp_path):
        """Transcribe returns a valid TranscriptResult."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_transcript = MagicMock()
        mock_transcript.text = "AssemblyAI transcription result"
        mock_transcript.confidence = 0.93
        mock_transcript.words = None
        mock_transcript.audio_duration = 5000  # milliseconds

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = mock_transcript

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            result = await provider.transcribe(str(audio_path))

        assert isinstance(result, TranscriptResult)
        assert result.text == "AssemblyAI transcription result"
        assert result.provider == "assemblyai"
        assert result.model == "assemblyai-default"
        assert result.confidence == 0.93
        assert result.duration_s == 5.0

    @pytest.mark.asyncio
    async def test_transcribe_with_word_timestamps(self, provider, tmp_path):
        """Transcribe with word-level timestamps returns structured words."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_word1 = MagicMock()
        mock_word1.text = "Hello"
        mock_word1.start = 0
        mock_word1.end = 500
        mock_word1.confidence = 0.95

        mock_word2 = MagicMock()
        mock_word2.text = "world"
        mock_word2.start = 500
        mock_word2.end = 1000
        mock_word2.confidence = 0.90

        mock_transcript = MagicMock()
        mock_transcript.text = "Hello world"
        mock_transcript.confidence = 0.92
        mock_transcript.words = [mock_word1, mock_word2]
        mock_transcript.audio_duration = 1000

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = mock_transcript

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            result = await provider.transcribe(str(audio_path))

        assert result.text == "Hello world"
        assert len(result.words) == 2
        assert result.words[0].word == "Hello"
        assert result.words[0].start == 0.0
        assert result.words[0].end == 0.5
        assert result.words[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_transcribe_raises_transient_on_service_error(self, provider, tmp_path):
        """Service error raises TransientProviderError."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        import assemblyai as aai
        mock_error = aai.AssemblyAIError("Service unavailable")
        mock_error.status_code = 503

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.side_effect = mock_error

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with pytest.raises(TransientProviderError):
                await provider.transcribe(str(audio_path))

    @pytest.mark.asyncio
    async def test_transcribe_raises_permanent_on_auth_error(self, provider, tmp_path):
        """Authentication error raises PermanentProviderError."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        import assemblyai as aai
        mock_error = aai.AssemblyAIError("Invalid API key")
        mock_error.status_code = 401

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.side_effect = mock_error

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with pytest.raises(PermanentProviderError):
                await provider.transcribe(str(audio_path))

    @pytest.mark.asyncio
    async def test_supports_file_returns_true(self, provider, tmp_path):
        """Supports file returns True for existing files."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"audio data")

        result = await provider.supports_file(str(audio_path))
        assert result is True

    @pytest.mark.asyncio
    async def test_supports_file_false_for_missing_file(self, provider):
        """Supports file returns False for non-existent file."""
        result = await provider.supports_file("/nonexistent/audio.wav")
        assert result is False

    @pytest.mark.asyncio
    async def test_missing_file_raises_permanent_error(self, provider):
        """Non-existent audio file raises PermanentProviderError."""
        with pytest.raises(PermanentProviderError) as exc_info:
            await provider.transcribe("/nonexistent/audio.wav")
        assert "not found" in str(exc_info.value)
