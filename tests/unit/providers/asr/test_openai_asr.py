"""Tests for OpenAIASRProvider implementation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.providers.asr.base import TranscriptResult
from src.providers.asr.openai_asr import OpenAIASRProvider
from src.utils.errors import PermanentProviderError, TransientProviderError


class TestOpenAIASRProvider:
    """Test OpenAIASRProvider with mocked OpenAI client."""

    @pytest.fixture
    def provider(self):
        """Create OpenAIASRProvider with test API key."""
        os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
        return OpenAIASRProvider(api_key="test-openai-api-key")

    def test_provider_name_and_model(self, provider):
        """Provider identifies itself correctly."""
        assert provider.name == "openai"
        assert provider.model == "whisper-1"

    def test_provider_custom_model(self):
        """Provider accepts a custom model name."""
        os.environ["OPENAI_API_KEY"] = "test-openai-api-key"
        provider = OpenAIASRProvider(api_key="test-openai-api-key", model="whisper-1")
        assert provider.model == "whisper-1"

    def test_missing_api_key_raises(self):
        """Missing API key raises PermanentProviderError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(PermanentProviderError) as exc_info:
                OpenAIASRProvider()
            assert "OPENAI_API_KEY" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transcribe_returns_transcript_result(self, provider, tmp_path):
        """Transcribe returns a valid TranscriptResult."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_client = MagicMock()
        # response_format="text" returns a plain string
        mock_client.audio.transcriptions.create.return_value = "OpenAI Whisper transcription result"

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_client):
            result = await provider.transcribe(str(audio_path))

        assert isinstance(result, TranscriptResult)
        assert result.text == "OpenAI Whisper transcription result"
        assert result.provider == "openai"
        assert result.model == "whisper-1"
        assert result.words == []  # OpenAI basic API doesn't return word timestamps

    @pytest.mark.asyncio
    async def test_transcribe_with_language(self, provider, tmp_path):
        """Transcribe sends the configured language parameter."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Transcripción en español"

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_client):
            await provider.transcribe(str(audio_path))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["language"] == "es"

    @pytest.mark.asyncio
    async def test_transcribe_raises_transient_on_rate_limit(self, provider, tmp_path):
        """Rate limit raises TransientProviderError."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        from openai import RateLimitError
        mock_error = RateLimitError(message="Rate limited", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = mock_error

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_client):
            with pytest.raises(TransientProviderError):
                await provider.transcribe(str(audio_path))

    @pytest.mark.asyncio
    async def test_transcribe_raises_permanent_on_auth_error(self, provider, tmp_path):
        """Authentication error raises PermanentProviderError."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        from openai import AuthenticationError
        mock_error = AuthenticationError(message="Bad API key", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = mock_error

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_client):
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
    async def test_supports_file_false_for_large_file(self, provider, tmp_path):
        """Supports file returns False for files exceeding 25MB limit."""
        audio_path = tmp_path / "big.wav"
        audio_path.write_bytes(b"x" * (30 * 1024 * 1024))

        result = await provider.supports_file(str(audio_path))
        assert result is False

    @pytest.mark.asyncio
    async def test_missing_file_raises_permanent_error(self, provider):
        """Non-existent audio file raises PermanentProviderError."""
        with pytest.raises(PermanentProviderError) as exc_info:
            await provider.transcribe("/nonexistent/audio.wav")
        assert "not found" in str(exc_info.value)
