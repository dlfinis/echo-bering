"""Tests for GroqLLMProvider implementation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.providers.llm.base import LLMResponse
from src.providers.llm.groq_llm import GroqLLMProvider
from src.utils.errors import PermanentProviderError, TransientProviderError


class TestGroqLLMProvider:
    """Test GroqLLMProvider with mocked Groq client."""

    @pytest.fixture
    def provider(self):
        """Create GroqLLMProvider with test API key."""
        os.environ["GROQ_API_KEY"] = "test-groq-api-key"
        return GroqLLMProvider(api_key="test-groq-api-key")

    def test_provider_name_and_model(self, provider):
        """Provider identifies itself correctly."""
        assert provider.name == "groq"
        assert provider.model == "llama-3.3-70b-versatile"

    def test_provider_custom_model(self):
        """Provider accepts a custom model name."""
        os.environ["GROQ_API_KEY"] = "test-groq-api-key"
        provider = GroqLLMProvider(api_key="test-groq-api-key", model="llama-4-scorpion")
        assert provider.model == "llama-4-scorpion"

    def test_missing_api_key_raises(self):
        """Missing API key raises PermanentProviderError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(PermanentProviderError) as exc_info:
                GroqLLMProvider()
            assert "GROQ_API_KEY" in str(exc_info.value)

    def test_supports_json_mode(self, provider):
        """Groq supports JSON response format."""
        assert provider.supports_json_mode() is True

    @pytest.mark.asyncio
    async def test_generate_returns_llm_response(self, provider):
        """Generate returns a valid LLMResponse."""
        mock_choice = MagicMock()
        mock_choice.message.content = "Groq LLM response text"
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 200
        mock_usage.completion_tokens = 100
        mock_usage.total_tokens = 300

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.providers.llm.groq_llm.Groq", return_value=mock_client):
            result = await provider.generate("Hello Groq")

        assert isinstance(result, LLMResponse)
        assert result.text == "Groq LLM response text"
        assert result.provider == "groq"
        assert result.model == "llama-3.3-70b-versatile"
        assert result.usage["total_tokens"] == 300

    @pytest.mark.asyncio
    async def test_generate_with_json_response_format(self, provider):
        """Generate sets JSON response format when requested."""
        mock_choice = MagicMock()
        mock_choice.message.content = '{"key": "value"}'
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 10
        mock_usage.total_tokens = 20

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.providers.llm.groq_llm.Groq", return_value=mock_client):
            await provider.generate("Return JSON", response_format="json")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"]["type"] == "json_object"

    @pytest.mark.asyncio
    async def test_generate_raises_transient_on_rate_limit(self, provider):
        """Rate limit raises TransientProviderError."""
        from groq import RateLimitError
        mock_error = RateLimitError(message="Rate limited", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_error

        with patch("src.providers.llm.groq_llm.Groq", return_value=mock_client):
            with pytest.raises(TransientProviderError):
                await provider.generate("test")

    @pytest.mark.asyncio
    async def test_generate_raises_permanent_on_auth_error(self, provider):
        """Authentication error raises PermanentProviderError."""
        from groq import AuthenticationError
        mock_error = AuthenticationError(message="Bad key", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_error

        with patch("src.providers.llm.groq_llm.Groq", return_value=mock_client):
            with pytest.raises(PermanentProviderError):
                await provider.generate("test")
