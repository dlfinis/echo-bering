"""Tests for GroqASRProvider implementation."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.asr.groq_asr import GroqASRProvider
from src.utils.errors import PermanentProviderError, TransientProviderError


class TestGroqASRProvider:
    """Test GroqASRProvider with mocked Groq client."""

    @pytest.fixture
    def provider(self):
        """Create GroqASRProvider with test API key."""
        os.environ["GROQ_API_KEY"] = "test-groq-api-key"
        return GroqASRProvider(api_key="test-groq-api-key")

    def test_provider_name_and_model(self, provider):
        """Provider identifies itself correctly."""
        assert provider.name == "groq"
        assert provider.model == "whisper-large-v3-turbo"

    def test_provider_custom_model(self):
        """Provider accepts a custom model name."""
        os.environ["GROQ_API_KEY"] = "test-groq-api-key"
        provider = GroqASRProvider(api_key="test-groq-api-key", model="whisper-large-v3")
        assert provider.model == "whisper-large-v3"

    def test_missing_api_key_raises(self):
        """Missing API key raises PermanentProviderError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(PermanentProviderError) as exc_info:
                GroqASRProvider()
            assert "GROQ_API_KEY" in str(exc_info.value)

    def _create_mock_client(self, response: MagicMock) -> MagicMock:
        """Helper to create a mocked Groq client with given response."""
        mock_client = MagicMock()
        mock_transcriptions = MagicMock()
        mock_transcriptions.create.return_value = response
        mock_client.audio = MagicMock()
        mock_client.audio.transcriptions = mock_transcriptions
        return mock_client

    @pytest.mark.asyncio
    async def test_transcribe_returns_transcript_result(self, provider, tmp_path):
        """Transcribe returns a valid TranscriptResult."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_response = MagicMock()
        mock_response.text = "Hello world this is a test transcription"
        mock_response.language = "en"
        mock_response.words = None

        mock_client = self._create_mock_client(mock_response)

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            result = await provider.transcribe(str(audio_path))

        assert isinstance(result, TranscriptResult)
        assert result.text == "Hello world this is a test transcription"
        assert result.provider == "groq"
        assert result.model == "whisper-large-v3-turbo"

    @pytest.mark.asyncio
    async def test_transcribe_with_verbose_response(self, provider, tmp_path):
        """Transcribe with verbose response returns word-level timestamps."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_word1 = MagicMock()
        mock_word1.word = "Hello"
        mock_word1.start = 0.0
        mock_word1.end = 0.5
        mock_word1.confidence = 0.95

        mock_word2 = MagicMock()
        mock_word2.word = "world"
        mock_word2.start = 0.5
        mock_word2.end = 1.0
        mock_word2.confidence = 0.92

        mock_response = MagicMock()
        mock_response.text = "Hello world"
        mock_response.language = "en"
        mock_response.words = [mock_word1, mock_word2]
        mock_response.duration = 1.0

        mock_client = self._create_mock_client(mock_response)

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            result = await provider.transcribe(str(audio_path))

        assert result.text == "Hello world"
        assert len(result.words) == 2
        assert result.words[0].word == "Hello"
        assert result.words[0].start == 0.0
        assert result.words[0].end == 0.5
        assert result.words[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_transcribe_without_word_timestamps(self, provider, tmp_path):
        """Transcribe without word timestamps returns empty words list."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_response = MagicMock()
        mock_response.text = "Just text without words"
        mock_response.language = "en"
        mock_response.words = None

        mock_client = self._create_mock_client(mock_response)

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            result = await provider.transcribe(str(audio_path))

        assert result.text == "Just text without words"
        assert result.words == []

    @pytest.mark.asyncio
    async def test_transcribe_raises_transient_on_rate_limit(self, provider, tmp_path):
        """Rate limit (429) raises TransientProviderError."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        from groq import RateLimitError
        mock_error = RateLimitError(message="Rate limited", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_transcriptions = MagicMock()
        mock_transcriptions.create.side_effect = mock_error
        mock_client.audio = MagicMock()
        mock_client.audio.transcriptions = mock_transcriptions

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            with pytest.raises(TransientProviderError) as exc_info:
                await provider.transcribe(str(audio_path))
            assert 429 == exc_info.value.status_code

    @pytest.mark.asyncio
    async def test_transcribe_raises_permanent_on_auth_error(self, provider, tmp_path):
        """Authentication error (401) raises PermanentProviderError."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        from groq import AuthenticationError
        mock_error = AuthenticationError(message="Bad API key", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_transcriptions = MagicMock()
        mock_transcriptions.create.side_effect = mock_error
        mock_client.audio = MagicMock()
        mock_client.audio.transcriptions = mock_transcriptions

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            with pytest.raises(PermanentProviderError):
                await provider.transcribe(str(audio_path))

    @pytest.mark.asyncio
    async def test_supports_file_returns_true_for_valid_file(self, provider, tmp_path):
        """Supports file returns True for existing file within size limit."""
        audio_path = tmp_path / "test.wav"
        # Create a 10MB file (under 25MB limit)
        audio_path.write_bytes(b"x" * (10 * 1024 * 1024))

        result = await provider.supports_file(str(audio_path))
        assert result is True

    @pytest.mark.asyncio
    async def test_supports_file_false_for_large_file(self, provider, tmp_path):
        """Supports file returns False for files exceeding size limit."""
        audio_path = tmp_path / "big.wav"
        # Create a 30MB file (over 25MB limit)
        audio_path.write_bytes(b"x" * (30 * 1024 * 1024))

        result = await provider.supports_file(str(audio_path))
        assert result is False

    @pytest.mark.asyncio
    async def test_supports_file_false_for_missing_file(self, provider):
        """Supports file returns False for non-existent file."""
        result = await provider.supports_file("/nonexistent/audio.wav")
        assert result is False

    @pytest.mark.asyncio
    async def test_transcribe_opens_file_for_reading(self, provider, tmp_path):
        """Transcribe opens the audio file in binary mode."""
        audio_path = tmp_path / "audio.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_response = MagicMock()
        mock_response.text = "transcribed"
        mock_response.language = "en"
        mock_response.words = None

        mock_client = self._create_mock_client(mock_response)
        mock_transcriptions = mock_client.audio.transcriptions

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            await provider.transcribe(str(audio_path))

        # Verify the call was made with file parameter
        call_kwargs = mock_transcriptions.create.call_args.kwargs
        assert "file" in call_kwargs
        assert "model" in call_kwargs
        assert call_kwargs["model"] == "whisper-large-v3-turbo"

    @pytest.mark.asyncio
    async def test_missing_file_raises_permanent_error(self, provider):
        """Non-existent audio file raises PermanentProviderError."""
        with pytest.raises(PermanentProviderError) as exc_info:
            await provider.transcribe("/nonexistent/audio.wav")
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transcribe_raises_transient_on_server_error(self, provider, tmp_path):
        """500-level server errors raise TransientProviderError."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        from groq import APIStatusError
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_error = APIStatusError(
            message="Internal server error",
            response=mock_response,
            body=None,
        )

        mock_client = MagicMock()
        mock_transcriptions = MagicMock()
        mock_transcriptions.create.side_effect = mock_error
        mock_client.audio = MagicMock()
        mock_client.audio.transcriptions = mock_transcriptions

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            with pytest.raises(TransientProviderError) as exc_info:
                await provider.transcribe(str(audio_path))
            assert 500 == exc_info.value.status_code

    @pytest.mark.asyncio
    async def test_transcribe_raises_permanent_on_api_error(self, provider, tmp_path):
        """400-level API errors raise PermanentProviderError."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        from groq import APIStatusError
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_error = APIStatusError(
            message="Bad request",
            response=mock_response,
            body=None,
        )

        mock_client = MagicMock()
        mock_transcriptions = MagicMock()
        mock_transcriptions.create.side_effect = mock_error
        mock_client.audio = MagicMock()
        mock_client.audio.transcriptions = mock_transcriptions

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            with pytest.raises(PermanentProviderError) as exc_info:
                await provider.transcribe(str(audio_path))
            assert 400 == exc_info.value.status_code

    @pytest.mark.asyncio
    async def test_transcribe_raises_permanent_on_unknown_error(self, provider, tmp_path):
        """Non-Groq errors during transcribe are propagated."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        mock_client = MagicMock()
        mock_transcriptions = MagicMock()
        mock_transcriptions.create.side_effect = ConnectionError("Network unreachable")
        mock_client.audio = MagicMock()
        mock_client.audio.transcriptions = mock_transcriptions

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_client):
            with pytest.raises(ConnectionError):
                await provider.transcribe(str(audio_path))

    def test_calculate_confidence_empty_words(self, provider):
        """Returns 1.0 confidence when no words provided."""
        result = GroqASRProvider._calculate_confidence([])
        assert result == 1.0

    def test_extract_duration_from_response(self, provider):
        """Extracts duration from response.duration attribute."""
        mock_response = MagicMock()
        mock_response.duration = 42.5
        mock_response.words = None

        result = GroqASRProvider._extract_duration(mock_response)
        assert result == 42.5

    def test_extract_duration_from_words_fallback(self, provider):
        """Falls back to last word end time when duration not available."""
        mock_word = MagicMock()
        mock_word.end = 15.5

        mock_response = MagicMock()
        mock_response.duration = None
        mock_response.words = [mock_word]

        result = GroqASRProvider._extract_duration(mock_response)
        assert result == 15.5

    def test_extract_duration_no_data(self, provider):
        """Returns 0.0 when no duration or words available."""
        mock_response = MagicMock()
        mock_response.duration = None
        mock_response.words = None

        result = GroqASRProvider._extract_duration(mock_response)
        assert result == 0.0
