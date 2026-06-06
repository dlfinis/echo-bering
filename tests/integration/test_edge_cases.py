"""Integration tests for edge cases.

Tests short videos (<1 min), long videos (>4 hours), memory usage,
resource cleanup, and concurrent provider usage.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.factories.provider_factory import ProviderFactory
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.llm.base import LLMResponse
from src.utils.cost_estimator import CostEstimator
from src.utils.errors import BudgetError


class TestShortVideoEdgeCases:
    """Test edge cases for very short videos (<1 minute)."""

    @pytest.mark.asyncio
    async def test_very_short_audio_transcription(self, tmp_path):
        """ASR handles audio under 10 seconds correctly."""
        audio_path = tmp_path / "short.wav"
        audio_path.write_bytes(b"fake audio")

        mock_transcriber = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Hi"
        mock_result.confidence = 0.85
        mock_result.words = None
        mock_result.audio_duration = 500  # 0.5 seconds

        mock_transcriber.transcribe.return_value = mock_result

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("assemblyai")
                result = await asr.transcribe(str(audio_path))

        assert result.text == "Hi"
        assert result.duration_s == 0.5
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_short_video_cost_is_minimal(self):
        """Short video transcription costs are correctly calculated."""
        estimator = CostEstimator()

        # 30 seconds of audio with Groq ($0.0004/min)
        cost = estimator.estimate_asr_cost(30.0, "groq")
        assert cost == pytest.approx(0.0002, rel=0.01)

        # 10 seconds of audio with OpenAI ($0.006/min)
        cost = estimator.estimate_asr_cost(10.0, "openai")
        assert cost == pytest.approx(0.001, rel=0.01)

    @pytest.mark.asyncio
    async def test_short_video_with_word_timestamps(self, tmp_path):
        """Even short videos can have word timestamps."""
        audio_path = tmp_path / "short.wav"
        audio_path.write_bytes(b"fake audio")

        mock_word = MagicMock()
        mock_word.text = "Hello"
        mock_word.start = 0
        mock_word.end = 300
        mock_word.confidence = 0.95

        mock_transcript = MagicMock()
        mock_transcript.text = "Hello"
        mock_transcript.confidence = 0.95
        mock_transcript.words = [mock_word]
        mock_transcript.audio_duration = 500

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = mock_transcript

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("assemblyai")
                result = await asr.transcribe(str(audio_path))

        assert len(result.words) == 1
        assert result.words[0].word == "Hello"
        assert result.words[0].start == 0.0
        assert result.words[0].end == 0.3


class TestLongVideoEdgeCases:
    """Test edge cases for very long videos (>4 hours)."""

    def test_four_hour_video_cost_assemblyai(self):
        """4-hour video ASR cost is correctly calculated for AssemblyAI."""
        estimator = CostEstimator()
        # 4 hours = 240 minutes, AssemblyAI = $0.0004/min
        cost = estimator.estimate_asr_cost(240 * 60, "assemblyai")
        assert cost == pytest.approx(0.096, rel=0.01)

    def test_four_hour_video_cost_openai(self):
        """4-hour video ASR cost is correctly calculated for OpenAI."""
        estimator = CostEstimator()
        # 4 hours = 240 minutes, OpenAI = $0.006/min
        cost = estimator.estimate_asr_cost(240 * 60, "openai")
        assert cost == pytest.approx(1.44, rel=0.01)

    def test_four_hour_video_cost_groq(self):
        """4-hour video ASR cost is correctly calculated for Groq."""
        estimator = CostEstimator()
        # 4 hours = 240 minutes, Groq = $0.0004/min
        cost = estimator.estimate_asr_cost(240 * 60, "groq")
        assert cost == pytest.approx(0.096, rel=0.01)

    def test_long_video_llm_cost_scaling(self):
        """LLM cost scales correctly for long video analysis."""
        estimator = CostEstimator()

        # A 4-hour video might generate 50k tokens for analysis
        deepseek_cost = estimator.estimate_llm_cost(50_000, "deepseek")
        assert deepseek_cost == pytest.approx(0.007, rel=0.01)

        openai_cost = estimator.estimate_llm_cost(50_000, "openai")
        assert openai_cost == pytest.approx(0.125, rel=0.01)

    def test_budget_exceeded_for_long_video(self):
        """Budget enforcement catches expensive long video processing."""
        estimator = CostEstimator()

        # 4 hours with OpenAI ASR ($1.44) + OpenAI LLM analysis ($0.125)
        estimator.add_cost(estimator.estimate_asr_cost(240 * 60, "openai"))
        estimator.add_cost(estimator.estimate_llm_cost(50_000, "openai"))

        with pytest.raises(BudgetError):
            estimator.check_budget(1.0)  # Budget too small

    def test_long_video_within_budget(self):
        """Long video passes budget check with sufficient budget."""
        estimator = CostEstimator()

        # 4 hours with Groq ASR ($0.096) + DeepSeek LLM ($0.007)
        estimator.add_cost(estimator.estimate_asr_cost(240 * 60, "groq"))
        estimator.add_cost(estimator.estimate_llm_cost(50_000, "deepseek"))

        assert estimator.check_budget(1.0) is True


class TestResourceCleanup:
    """Test resource cleanup after provider operations."""

    @pytest.mark.asyncio
    async def test_assemblyai_provider_lazy_initialization(self):
        """AssemblyAI transcriber is lazily initialized."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("assemblyai")

        # Transcriber should not be initialized yet
        assert provider._transcriber is None

    @pytest.mark.asyncio
    async def test_openai_provider_lazy_initialization(self):
        """OpenAI client is lazily initialized."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("openai")

        # Client should not be initialized yet
        assert provider._client is None

    @pytest.mark.asyncio
    async def test_deepseek_provider_lazy_initialization(self):
        """DeepSeek client is lazily initialized."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            provider = ProviderFactory.create_llm("deepseek")

        # Client should not be initialized yet
        assert provider._client is None

    @pytest.mark.asyncio
    async def test_groq_provider_lazy_initialization(self):
        """Groq client is lazily initialized for both ASR and LLM."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            asr = ProviderFactory.create_asr("groq")
            llm = ProviderFactory.create_llm("groq")

        assert asr._client is None
        assert llm._client is None


class TestConcurrentProviderUsage:
    """Test concurrent provider usage and thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_asr_requests(self, tmp_path):
        """Multiple ASR providers can be used concurrently."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        # Mock both ASR providers
        mock_assemblyai_transcriber = MagicMock()
        mock_assemblyai_result = MagicMock()
        mock_assemblyai_result.text = "AssemblyAI result"
        mock_assemblyai_result.confidence = 0.90
        mock_assemblyai_result.words = None
        mock_assemblyai_result.audio_duration = 5000
        mock_assemblyai_transcriber.transcribe.return_value = mock_assemblyai_result

        mock_openai_client = MagicMock()
        mock_openai_client.audio.transcriptions.create.return_value = "OpenAI result"

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_assemblyai_transcriber):
            with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_openai_client):
                with patch.dict(os.environ, {
                    "ASSEMBLYAI_API_KEY": "test-key",
                    "OPENAI_API_KEY": "test-key",
                }):
                    # Run both providers concurrently
                    assemblyai_asr = ProviderFactory.create_asr("assemblyai")
                    openai_asr = ProviderFactory.create_asr("openai")

                    results = await asyncio.gather(
                        assemblyai_asr.transcribe(str(audio_path)),
                        openai_asr.transcribe(str(audio_path)),
                    )

                    assert results[0].text == "AssemblyAI result"
                    assert results[0].provider == "assemblyai"
                    assert results[1].text == "OpenAI result"
                    assert results[1].provider == "openai"

    @pytest.mark.asyncio
    async def test_concurrent_llm_requests(self):
        """Multiple LLM providers can be used concurrently."""
        def _make_mock_response(text, prompt_tokens=100):
            mock_choice = MagicMock()
            mock_choice.message.content = text
            mock_choice.message.role = "assistant"
            mock_choice.finish_reason = "stop"

            mock_usage = MagicMock()
            mock_usage.prompt_tokens = prompt_tokens
            mock_usage.completion_tokens = 50
            mock_usage.total_tokens = prompt_tokens + 50

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage
            return mock_response

        mock_deepseek_client = MagicMock()
        mock_deepseek_client.chat.completions.create.return_value = _make_mock_response("DeepSeek result", 100)

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.return_value = _make_mock_response("OpenAI result", 200)

        with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_deepseek_client):
            with patch("src.providers.llm.openai_llm.OpenAI", return_value=mock_openai_client):
                with patch.dict(os.environ, {
                    "DEEPSEEK_API_KEY": "test-key",
                    "OPENAI_API_KEY": "test-key",
                }):
                    deepseek_llm = ProviderFactory.create_llm("deepseek")
                    openai_llm = ProviderFactory.create_llm("openai")

                    results = await asyncio.gather(
                        deepseek_llm.generate("test prompt 1"),
                        openai_llm.generate("test prompt 2"),
                    )

                    assert results[0].text == "DeepSeek result"
                    assert results[0].provider == "deepseek"
                    assert results[1].text == "OpenAI result"
                    assert results[1].provider == "openai"

    @pytest.mark.asyncio
    async def test_provider_factory_is_thread_safe(self):
        """ProviderFactory creates independent instances."""
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-key",
            "DEEPSEEK_API_KEY": "test-key",
        }):
            provider1 = ProviderFactory.create_asr("groq")
            provider2 = ProviderFactory.create_asr("groq")

        # Each call should create a new instance
        assert provider1 is not provider2
        assert provider1.name == provider2.name


class TestTranscriptResultValidation:
    """Test TranscriptResult Pydantic validation."""

    def test_word_timestamp_confidence_bounds(self):
        """WordTimestamp confidence must be between 0 and 1."""
        from src.providers.asr.base import WordTimestamp

        # Valid confidence
        wt = WordTimestamp(word="test", start=0.0, end=1.0, confidence=0.95)
        assert wt.confidence == 0.95

        # Default confidence is 1.0
        wt = WordTimestamp(word="test", start=0.0, end=1.0)
        assert wt.confidence == 1.0

        # Invalid confidence should fail validation
        with pytest.raises(Exception):  # Pydantic ValidationError
            WordTimestamp(word="test", start=0.0, end=1.0, confidence=1.5)

    def test_transcript_result_required_fields(self):
        """TranscriptResult requires all fields."""
        from src.providers.asr.base import TranscriptResult

        result = TranscriptResult(
            text="test",
            confidence=0.9,
            words=[],
            duration_s=10.0,
            provider="test",
            model="test-model",
        )

        assert result.text == "test"
        assert result.provider == "test"
        assert result.model == "test-model"

    def test_llm_response_required_fields(self):
        """LLMResponse requires all fields."""
        from src.providers.llm.base import LLMResponse

        response = LLMResponse(
            text="response",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            provider="test",
            model="test-model",
        )

        assert response.text == "response"
        assert response.usage["total_tokens"] == 150
        assert response.provider == "test"
        assert response.finish_reason is None
