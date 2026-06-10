"""Integration tests for Groq ASR + DeepSeek LLM provider combination.

Tests the primary production combination with mocked API calls,
validating cross-provider compatibility and pipeline data flow.
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.factories.provider_factory import ProviderFactory
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.llm.base import LLMResponse


def _make_groq_transcript():
    """Create a realistic Groq transcription result."""
    return TranscriptResult(
        text="Welcome to this tutorial on Python programming. "
             "In this first section, we will cover the basics of variables and data types. "
             "Python is a dynamically typed language, which means you don't need to declare "
             "the type of a variable when you create it.",
        confidence=0.94,
        words=[
            WordTimestamp(word="Welcome", start=0.0, end=0.4, confidence=0.96),
            WordTimestamp(word="to", start=0.5, end=0.7, confidence=0.95),
            WordTimestamp(word="this", start=0.8, end=1.0, confidence=0.94),
            WordTimestamp(word="tutorial", start=1.1, end=1.6, confidence=0.93),
            WordTimestamp(word="on", start=1.7, end=1.9, confidence=0.95),
            WordTimestamp(word="Python", start=2.0, end=2.5, confidence=0.97),
            WordTimestamp(word="programming.", start=2.6, end=3.2, confidence=0.92),
        ],
        duration_s=180.0,
        provider="groq",
        model="whisper-large-v3-turbo",
    )


def _make_deepseek_response(text="Chapter analysis response"):
    """Create a realistic DeepSeek LLM response."""
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_choice.message.role = "assistant"
    mock_choice.finish_reason = "stop"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 500
    mock_usage.completion_tokens = 200
    mock_usage.total_tokens = 700

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    return mock_response


class TestGroqASRDeepSeekLLMIntegration:
    """Test Groq ASR + DeepSeek LLM as the primary production combination."""

    @pytest.fixture
    def groq_asr(self):
        """Create Groq ASR provider with mocked client."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}):
            return ProviderFactory.create_asr("groq")

    @pytest.fixture
    def deepseek_llm(self):
        """Create DeepSeek LLM provider with mocked client."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-deepseek-key"}):
            return ProviderFactory.create_llm("deepseek")

    def test_factory_creates_groq_asr(self):
        """Factory creates GroqASRProvider with correct type."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("groq")
        assert provider.name == "groq"

    def test_factory_creates_deepseek_llm(self):
        """Factory creates DeepSeekLLMProvider with correct type."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            provider = ProviderFactory.create_llm("deepseek")
        assert provider.name == "deepseek"

    @pytest.mark.asyncio
    async def test_groq_transcribe_to_deepseek_generate_flow(self, tmp_path):
        """Groq transcription output flows into DeepSeek LLM input."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        # Mock Groq ASR response
        mock_groq_response = MagicMock()
        mock_groq_response.text = _make_groq_transcript().text
        mock_groq_response.language = "en"
        mock_groq_response.words = None

        mock_groq_client = MagicMock()
        mock_groq_client.audio.transcriptions.create.return_value = mock_groq_response

        # Mock DeepSeek LLM response
        mock_deepseek_response = _make_deepseek_response(
            '{"chapters": [{"number": 1, "title": "Introduction", '
            '"start_time": "00:00:00.000", "end_time": "00:03:00.000", '
            '"start_seconds": 0.0, "end_seconds": 180.0, '
            '"confidence": 0.90, "transcript": "Welcome to this tutorial"}]}'
        )
        mock_deepseek_client = MagicMock()
        mock_deepseek_client.chat.completions.create.return_value = mock_deepseek_response

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_groq_client):
            with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_deepseek_client):
                # Step 1: Transcribe with Groq
                transcript = await ProviderFactory.create_asr("groq").transcribe(str(audio_path))

                assert isinstance(transcript, TranscriptResult)
                assert transcript.provider == "groq"
                assert transcript.confidence > 0.9

                # Step 2: Use transcript text with DeepSeek
                prompt = f"Analyze this transcript and create chapters:\n\n{transcript.text}"
                llm_result = await ProviderFactory.create_llm("deepseek").generate(
                    prompt,
                    system_prompt="You are an expert video content analyzer.",
                    response_format="json",
                )

                assert isinstance(llm_result, LLMResponse)
                assert llm_result.provider == "deepseek"
                assert "chapters" in llm_result.text

    @pytest.mark.asyncio
    async def test_groq_word_timestamps_preserved_through_pipeline(self, tmp_path):
        """Word timestamps from Groq are preserved and usable by downstream stages."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        mock_word = MagicMock()
        mock_word.word = "Python"
        mock_word.start = 2.0
        mock_word.end = 2.5
        mock_word.confidence = 0.97

        mock_groq_response = MagicMock()
        mock_groq_response.text = "Python programming"
        mock_groq_response.language = "en"
        mock_groq_response.words = [mock_word]
        mock_groq_response.duration = 3.0

        mock_groq_client = MagicMock()
        mock_groq_client.audio.transcriptions.create.return_value = mock_groq_response

        with patch("src.providers.asr.groq_asr.Groq", return_value=mock_groq_client):
            result = await ProviderFactory.create_asr("groq").transcribe(str(audio_path))

        assert len(result.words) == 1
        assert result.words[0].word == "Python"
        assert result.words[0].start == 2.0
        assert result.words[0].confidence == 0.97

    def test_provider_combination_metadata(self):
        """Both providers report correct metadata for pipeline tracking."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            asr = ProviderFactory.create_asr("groq")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            llm = ProviderFactory.create_llm("deepseek")

        assert asr.name == "groq"
        assert asr.model == "whisper-large-v3-turbo"
        assert llm.name == "deepseek"
        assert llm.model == "deepseek-chat"

    def test_both_providers_support_json_mode(self):
        """DeepSeek supports JSON mode (ASR providers don't have this concept)."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            llm = ProviderFactory.create_llm("deepseek")
        assert llm.supports_json_mode() is True
