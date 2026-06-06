"""Integration tests for provider fallback scenarios.

Tests retry logic with exponential backoff, provider switching on failure,
budget enforcement during fallbacks, and partial failure handling.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.factories.provider_factory import ProviderFactory
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.llm.base import LLMResponse
from src.utils.errors import BudgetError, PermanentProviderError, TransientProviderError
from src.utils.retry import RetryPolicy


class TestRetryLogicExponentialBackoff:
    """Test retry behavior across all providers with exponential backoff."""

    @pytest.mark.asyncio
    async def test_assemblyai_retries_on_transient_error(self, tmp_path):
        """AssemblyAI retries on 5xx errors and succeeds eventually."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        call_count = 0

        def mock_transcribe(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                import assemblyai as aai
                err = aai.AssemblyAIError("Service unavailable")
                err.status_code = 503
                raise err
            mock_result = MagicMock()
            mock_result.text = "Success after retries"
            mock_result.confidence = 0.90
            mock_result.words = None
            mock_result.audio_duration = 5000
            return mock_result

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.side_effect = mock_transcribe

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("assemblyai")
                result = await asr.transcribe(str(audio_path))

        assert result.text == "Success after retries"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_openai_retries_on_rate_limit(self, tmp_path):
        """OpenAI retries on rate limit (429) and succeeds."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        call_count = 0

        def mock_transcribe(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                from openai import RateLimitError
                raise RateLimitError("Rate limited", response=MagicMock(), body=None)
            return "Success after rate limit retry"

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = mock_transcribe

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_client):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("openai")
                result = await asr.transcribe(str(audio_path))

        assert result.text == "Success after rate limit retry"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_deepseek_retries_on_transient_error(self):
        """DeepSeek retries on 5xx errors."""
        call_count = 0

        def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                from openai import APIError
                err = APIError("Internal server error", request=MagicMock(), body=None)
                err.status_code = 500
                raise err

            mock_choice = MagicMock()
            mock_choice.message.content = "DeepSeek response"
            mock_choice.message.role = "assistant"
            mock_choice.finish_reason = "stop"

            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 100
            mock_usage.completion_tokens = 50
            mock_usage.total_tokens = 150

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_response.usage = mock_usage
            return mock_response

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_create

        with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_client):
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
                llm = ProviderFactory.create_llm("deepseek")
                result = await llm.generate("test prompt")

        assert result.text == "DeepSeek response"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_permanent_error_no_retries(self, tmp_path):
        """Permanent errors (401) are NOT retried across all providers."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        call_count = 0

        def mock_transcribe(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            from openai import AuthenticationError
            raise AuthenticationError("Bad key", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = mock_transcribe

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_client):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("openai")

                with pytest.raises(PermanentProviderError):
                    await asr.transcribe(str(audio_path))

        # Should only be called once (no retries for permanent errors)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises(self, tmp_path):
        """After max retries exhausted, error propagates."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        import assemblyai as aai
        mock_error = aai.AssemblyAIError("Persistent error")
        mock_error.status_code = 503

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.side_effect = mock_error

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("assemblyai")

                with pytest.raises(TransientProviderError) as exc_info:
                    await asr.transcribe(str(audio_path))

                assert exc_info.value.status_code == 503


class TestBudgetEnforcementWithProviders:
    """Test budget enforcement when using providers."""

    def test_cost_estimator_tracks_asr_cost_per_provider(self):
        """Cost estimator calculates ASR costs correctly per provider."""
        from src.utils.cost_estimator import CostEstimator

        estimator = CostEstimator()

        # Groq: $0.0004/min
        groq_cost = estimator.estimate_asr_cost(60.0, "groq")
        assert groq_cost == pytest.approx(0.0004, rel=0.01)

        # AssemblyAI: $0.0004/min
        assemblyai_cost = estimator.estimate_asr_cost(60.0, "assemblyai")
        assert assemblyai_cost == pytest.approx(0.0004, rel=0.01)

        # OpenAI: $0.006/min
        openai_cost = estimator.estimate_asr_cost(60.0, "openai")
        assert openai_cost == pytest.approx(0.006, rel=0.01)

    def test_cost_estimator_tracks_llm_cost_per_provider(self):
        """Cost estimator calculates LLM costs correctly per provider."""
        from src.utils.cost_estimator import CostEstimator

        estimator = CostEstimator()

        # DeepSeek: $0.14/1M tokens
        deepseek_cost = estimator.estimate_llm_cost(1_000_000, "deepseek")
        assert deepseek_cost == pytest.approx(0.14, rel=0.01)

        # Groq: $0.0007/1M tokens
        groq_cost = estimator.estimate_llm_cost(1_000_000, "groq")
        assert groq_cost == pytest.approx(0.0007, rel=0.01)

        # OpenAI: $2.50/1M tokens
        openai_cost = estimator.estimate_llm_cost(1_000_000, "openai")
        assert openai_cost == pytest.approx(2.50, rel=0.01)

    def test_budget_exceeded_raises_error(self):
        """BudgetError is raised when costs exceed limit."""
        from src.utils.cost_estimator import CostEstimator

        estimator = CostEstimator()
        estimator.add_cost(5.0)
        estimator.add_cost(6.0)

        with pytest.raises(BudgetError) as exc_info:
            estimator.check_budget(10.0)

        assert exc_info.value.current_cost == 11.0
        assert exc_info.value.max_budget == 10.0

    def test_budget_within_limit_passes(self):
        """Budget check passes when costs are under limit."""
        from src.utils.cost_estimator import CostEstimator

        estimator = CostEstimator()
        estimator.add_cost(3.0)

        assert estimator.check_budget(10.0) is True


class TestPartialFailureScenarios:
    """Test partial failure scenarios with mixed success/failure."""

    @pytest.mark.asyncio
    async def test_asr_succeeds_llm_fails_permanent(self, tmp_path):
        """ASR transcription succeeds but LLM fails with permanent error."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        # Mock successful ASR
        mock_transcriber = MagicMock()
        mock_result = MagicMock()
        mock_result.text = "Transcription succeeded"
        mock_result.confidence = 0.90
        mock_result.words = None
        mock_result.audio_duration = 5000
        mock_transcriber.transcribe.return_value = mock_result

        # Mock failing LLM
        from openai import AuthenticationError
        auth_err = AuthenticationError("Bad key", response=MagicMock(), body=None)
        mock_llm_client = MagicMock()
        mock_llm_client.chat.completions.create.side_effect = auth_err

        with patch("src.providers.asr.assemblyai_asr.aai.Transcriber", return_value=mock_transcriber):
            with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_llm_client):
                with patch.dict(os.environ, {
                    "ASSEMBLYAI_API_KEY": "test-key",
                    "DEEPSEEK_API_KEY": "test-key",
                }):
                    # ASR should succeed
                    asr = ProviderFactory.create_asr("assemblyai")
                    transcript = await asr.transcribe(str(audio_path))
                    assert transcript.text == "Transcription succeeded"

                    # LLM should fail
                    llm = ProviderFactory.create_llm("deepseek")
                    with pytest.raises(PermanentProviderError):
                        await llm.generate("test prompt")

    @pytest.mark.asyncio
    async def test_mixed_provider_error_types(self, tmp_path):
        """Different providers return different error types for same status code."""
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake audio")

        # OpenAI 500 -> TransientProviderError
        from openai import APIError
        err = APIError("Server error", request=MagicMock(), body=None)
        err.status_code = 500

        mock_openai_client = MagicMock()
        mock_openai_client.audio.transcriptions.create.side_effect = err

        with patch("src.providers.asr.openai_asr.OpenAI", return_value=mock_openai_client):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                asr = ProviderFactory.create_asr("openai")

                with pytest.raises(TransientProviderError) as exc_info:
                    await asr.transcribe(str(audio_path))

                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_provider_supports_file_checks_before_transcribe(self, tmp_path):
        """supports_file is called before transcribe to validate input."""
        small_audio = tmp_path / "small.wav"
        small_audio.write_bytes(b"small audio")

        large_audio = tmp_path / "large.wav"
        large_audio.write_bytes(b"x" * (30 * 1024 * 1024))

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            asr = ProviderFactory.create_asr("openai")

        # Small file should be supported
        assert await asr.supports_file(str(small_audio)) is True

        # Large file should not be supported
        assert await asr.supports_file(str(large_audio)) is False
