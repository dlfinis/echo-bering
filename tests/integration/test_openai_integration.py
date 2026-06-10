"""Integration tests for OpenAI ASR + OpenAI LLM provider combination.

Tests the fallback combination with OpenAI's Whisper ASR and GPT-4o-mini LLM,
validating the full provider stack with proper error handling and JSON mode support.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.factories.provider_factory import ProviderFactory
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.llm.base import LLMResponse


def _make_openai_asr_response():
    """Create a realistic OpenAI Whisper transcription response."""
    return TranscriptResult(
        text="Hello and welcome to our product demonstration. "
             "Today we will show you how our platform works. "
             "First, let us look at the main dashboard features.",
        confidence=1.0,  # OpenAI basic API doesn't return confidence
        words=[],  # OpenAI basic API doesn't return word timestamps
        duration_s=0.0,  # OpenAI basic API doesn't return duration
        provider="openai",
        model="whisper-1",
    )


def _make_openai_llm_response(text="OpenAI GPT response"):
    """Create a realistic OpenAI GPT-4o-mini LLM response."""
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_choice.message.role = "assistant"
    mock_choice.finish_reason = "stop"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 300
    mock_usage.completion_tokens = 150
    mock_usage.total_tokens = 450

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    return mock_response


class TestOpenAIASROpenAILLMIntegration:
    """Test OpenAI ASR + OpenAI LLM as the fallback combination."""

    @pytest.fixture
    def openai_asr(self):
        """Create OpenAI ASR provider with mocked client."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}):
            return ProviderFactory.create_asr("openai")

    @pytest.fixture
    def openai_llm(self):
        """Create OpenAI LLM provider with mocked client."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}):
            return ProviderFactory.create_llm("openai")

    def test_factory_creates_openai_asr(self):
        """Factory creates OpenAIASRProvider with correct type."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("openai")
        assert provider.name == "openai"
        assert provider.model == "whisper-1"

    def test_factory_creates_openai_llm(self):
        """Factory creates OpenAILLMProvider with correct type."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = ProviderFactory.create_llm("openai")
        assert provider.name == "openai"
        assert provider.model == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_openai_asr_to_llm_flow(self, tmp_path):
        """OpenAI Whisper transcription flows into GPT-4o-mini LLM."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        # Mock OpenAI ASR response
        mock_asr_client = MagicMock()
        mock_asr_client.audio.transcriptions.create.return_value = _make_openai_asr_response().text

        # Mock OpenAI LLM response
        mock_llm_response = _make_openai_llm_response(
            '{"chapters": [{"number": 1, "title": "Product Demo", '
            '"start_time": "00:00:00.000", "end_time": "00:02:00.000", '
            '"start_seconds": 0.0, "end_seconds": 120.0, '
            '"confidence": 0.88, "transcript": "Hello and welcome"}]}'
        )
        mock_llm_client = MagicMock()
        mock_llm_client.chat.completions.create.return_value = mock_llm_response

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_asr_client):
            with patch("src.providers.llm.openai_llm.OpenAI", return_value=mock_llm_client):
                with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                    # Step 1: Transcribe with OpenAI Whisper
                    transcript = await ProviderFactory.create_asr("openai").transcribe(str(audio_path))

                    assert isinstance(transcript, TranscriptResult)
                    assert transcript.provider == "openai"
                    assert transcript.model == "whisper-1"

                    # Step 2: Use transcript with OpenAI GPT
                    prompt = f"Create chapters from: {transcript.text}"
                    llm_result = await ProviderFactory.create_llm("openai").generate(
                        prompt,
                        system_prompt="You are a video content analyzer.",
                        response_format="json",
                    )

                    assert isinstance(llm_result, LLMResponse)
                    assert llm_result.provider == "openai"
                    assert llm_result.model == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_openai_asr_file_size_limit_enforced(self, tmp_path):
        """OpenAI ASR rejects files over 25MB."""
        large_audio = tmp_path / "large.wav"
        # Create a 30MB file (over Whisper's 25MB limit)
        large_audio.write_bytes(b"x" * (30 * 1024 * 1024))

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            asr = ProviderFactory.create_asr("openai")

        result = await asr.supports_file(str(large_audio))
        assert result is False

    @pytest.mark.asyncio
    async def test_openai_asr_accepts_valid_file(self, tmp_path):
        """OpenAI ASR accepts files under 25MB."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio data")

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            asr = ProviderFactory.create_asr("openai")

        result = await asr.supports_file(str(audio_path))
        assert result is True

    @pytest.mark.asyncio
    async def test_openai_llm_json_mode_format_set(self):
        """OpenAI LLM sets response_format to json_object when requested."""
        mock_llm_response = _make_openai_llm_response('{"result": "ok"}')
        mock_llm_client = MagicMock()
        mock_llm_client.chat.completions.create.return_value = mock_llm_response

        with patch("src.providers.llm.openai_llm.OpenAI", return_value=mock_llm_client):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                llm = ProviderFactory.create_llm("openai")
                await llm.generate("test", response_format="json")

        call_kwargs = mock_llm_client.chat.completions.create.call_args.kwargs
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"]["type"] == "json_object"

    def test_openai_providers_use_same_api_key(self):
        """Both OpenAI providers can share the same API key."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "shared-openai-key"}):
            asr = ProviderFactory.create_asr("openai")
            llm = ProviderFactory.create_llm("openai")

        assert asr.name == "openai"
        assert llm.name == "openai"

    @pytest.mark.asyncio
    async def test_openai_asr_language_parameter(self, tmp_path):
        """OpenAI ASR sends the configured language parameter."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = "Transcripci\u00f3n en espa\u00f1ol"

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_client):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("openai")
                await asr.transcribe(str(audio_path))

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["language"] == "es"
