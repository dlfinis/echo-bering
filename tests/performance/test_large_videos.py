"""Performance tests for large video processing.

Tests cost estimation, token budgeting, and resource scaling for
large videos (>1 hour) with various provider combinations.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.factories.provider_factory import ProviderFactory
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.llm.base import LLMResponse
from src.utils.cost_estimator import ASR_PRICES_PER_MINUTE, CostEstimator
from src.utils.errors import BudgetError


class TestLargeVideoCostEstimation:
    """Test cost estimation scales correctly for large videos."""

    @pytest.mark.parametrize("duration_minutes,provider,expected_cost_per_min", [
        (60, "groq", 0.0004),
        (60, "assemblyai", 0.0004),
        (60, "openai", 0.006),
        (120, "groq", 0.0004),
        (120, "assemblyai", 0.0004),
        (120, "openai", 0.006),
        (240, "groq", 0.0004),
        (240, "assemblyai", 0.0004),
        (240, "openai", 0.006),
    ])
    def test_asr_cost_scales_linearly_with_duration(self, duration_minutes, provider, expected_cost_per_min):
        """ASR cost scales linearly regardless of video length."""
        estimator = CostEstimator()
        duration_s = duration_minutes * 60

        cost = estimator.estimate_asr_cost(duration_s, provider)
        expected = duration_minutes * expected_cost_per_min

        assert cost == pytest.approx(expected, rel=0.01)

    def test_one_hour_groq_asr_cost(self):
        """1 hour of Groq ASR costs ~$0.024."""
        estimator = CostEstimator()
        cost = estimator.estimate_asr_cost(3600, "groq")
        assert cost == pytest.approx(0.024, rel=0.01)

    def test_one_hour_assemblyai_asr_cost(self):
        """1 hour of AssemblyAI ASR costs ~$0.024."""
        estimator = CostEstimator()
        cost = estimator.estimate_asr_cost(3600, "assemblyai")
        assert cost == pytest.approx(0.024, rel=0.01)

    def test_one_hour_openai_asr_cost(self):
        """1 hour of OpenAI ASR costs ~$0.36."""
        estimator = CostEstimator()
        cost = estimator.estimate_asr_cost(3600, "openai")
        assert cost == pytest.approx(0.36, rel=0.01)

    def test_two_hour_video_total_cost_groq_deepseek(self):
        """2-hour video with Groq ASR + DeepSeek LLM total cost estimate."""
        estimator = CostEstimator()

        # ASR: 2 hours = 120 minutes
        asr_cost = estimator.estimate_asr_cost(7200, "groq")

        # LLM: ~20k tokens for 2 hours of transcript analysis
        llm_cost = estimator.estimate_llm_cost(20_000, "deepseek")

        estimator.add_cost(asr_cost)
        estimator.add_cost(llm_cost)

        # Total should be well under $2 budget
        assert estimator.check_budget(2.0) is True
        assert estimator.total_cost < 0.10  # Should be very cheap

    def test_four_hour_video_total_cost_openai_openai(self):
        """4-hour video with OpenAI ASR + OpenAI LLM cost estimate."""
        estimator = CostEstimator()

        # ASR: 4 hours = 240 minutes
        asr_cost = estimator.estimate_asr_cost(14400, "openai")

        # LLM: ~50k tokens for 4 hours of transcript analysis
        llm_cost = estimator.estimate_llm_cost(50_000, "openai")

        estimator.add_cost(asr_cost)
        estimator.add_cost(llm_cost)

        # Total should exceed $1 budget (OpenAI is expensive)
        assert estimator.total_cost > 1.0

    def test_cheapest_combination_for_long_video(self):
        """Groq ASR + Groq LLM is cheapest for long videos."""
        estimator = CostEstimator()
        duration_s = 4 * 3600  # 4 hours

        # Groq + Groq
        asr_groq = estimator.estimate_asr_cost(duration_s, "groq")
        llm_groq = estimator.estimate_llm_cost(50_000, "groq")
        groq_total = asr_groq + llm_groq

        # AssemblyAI + DeepSeek
        asr_assemblyai = estimator.estimate_asr_cost(duration_s, "assemblyai")
        llm_deepseek = estimator.estimate_llm_cost(50_000, "deepseek")
        mixed_total = asr_assemblyai + llm_deepseek

        # OpenAI + OpenAI
        asr_openai = estimator.estimate_asr_cost(duration_s, "openai")
        llm_openai = estimator.estimate_llm_cost(50_000, "openai")
        openai_total = asr_openai + llm_openai

        # Groq + Groq should be cheapest
        assert groq_total < mixed_total
        assert groq_total < openai_total
        # OpenAI + OpenAI should be most expensive
        assert openai_total > groq_total
        assert openai_total > mixed_total


class TestLargeVideoProviderCompatibility:
    """Test provider behavior with large video transcript data."""

    @pytest.mark.asyncio
    async def test_assemblyai_handles_long_transcript(self, tmp_path):
        """AssemblyAI provider handles long transcript results."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        # Simulate a 4-hour transcript (~30,000 words)
        long_text = " ".join([f"Word{i}" for i in range(30_000)])

        mock_transcriber = MagicMock()
        mock_result = MagicMock()
        mock_result.text = long_text
        mock_result.confidence = 0.92
        mock_result.words = None
        mock_result.audio_duration = 14_400_000  # 4 hours in ms

        mock_transcriber.transcribe.return_value = mock_result

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("assemblyai")
                result = await asr.transcribe(str(audio_path))

        assert len(result.text) > 100_000  # Long text
        assert result.duration_s == 14_400.0  # 4 hours

    @pytest.mark.asyncio
    async def test_llm_handles_large_prompt(self):
        """LLM provider accepts large prompts without error."""
        # Simulate a 4-hour transcript as a prompt
        large_prompt = " ".join([f"Word{i}" for i in range(30_000)])

        mock_choice = MagicMock()
        mock_choice.message.content = '{"chapters": []}'
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 30_000
        mock_usage.completion_tokens = 100
        mock_usage.total_tokens = 30_100

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_client):
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
                llm = ProviderFactory.create_llm("deepseek")
                result = await llm.generate(large_prompt, response_format="json")

        assert result.usage["prompt_tokens"] == 30_000
        assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_word_timestamps_scale_with_duration(self, tmp_path):
        """Word timestamps scale correctly for long audio."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        # Simulate word timestamps for a long audio
        words = []
        for i in range(100):
            mock_word = MagicMock()
            mock_word.text = f"word{i}"
            mock_word.start = i * 1000  # ms
            mock_word.end = (i + 1) * 1000  # ms
            mock_word.confidence = 0.90 + (i % 10) * 0.01
            words.append(mock_word)

        mock_transcript = MagicMock()
        mock_transcript.text = " ".join([f"word{i}" for i in range(100)])
        mock_transcript.confidence = 0.92
        mock_transcript.words = words
        mock_transcript.audio_duration = 100_000  # ~100 seconds

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = mock_transcript

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("assemblyai")
                result = await asr.transcribe(str(audio_path))

        assert len(result.words) == 100
        # Last word should end at ~100 seconds
        assert result.words[-1].end == pytest.approx(100.0, rel=0.01)
        assert result.duration_s == 100.0


class TestPricingConstants:
    """Verify pricing constants are correctly defined."""

    def test_all_asr_providers_have_prices(self):
        """All registered ASR providers have pricing."""
        assert "groq" in ASR_PRICES_PER_MINUTE
        assert "assemblyai" in ASR_PRICES_PER_MINUTE
        assert "openai" in ASR_PRICES_PER_MINUTE

    def test_asr_prices_are_positive(self):
        """All ASR prices are positive."""
        for provider, price in ASR_PRICES_PER_MINUTE.items():
            assert price > 0, f"{provider} has invalid price: {price}"

    def test_openai_is_more_expensive_than_groq(self):
        """OpenAI ASR is more expensive than Groq."""
        assert ASR_PRICES_PER_MINUTE["openai"] > ASR_PRICES_PER_MINUTE["groq"]

    def test_openai_llm_is_more_expensive_than_deepseek(self):
        """OpenAI LLM is more expensive than DeepSeek."""
        from src.utils.cost_estimator import LLM_PRICES_PER_M_TOKENS

        assert LLM_PRICES_PER_M_TOKENS["openai"] > LLM_PRICES_PER_M_TOKENS["deepseek"]
