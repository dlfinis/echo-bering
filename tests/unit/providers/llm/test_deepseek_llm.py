"""Tests for DeepSeekLLMProvider implementation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.providers.llm.base import LLMResponse
from src.providers.llm.deepseek_llm import DeepSeekLLMProvider
from src.utils.errors import PermanentProviderError, TransientProviderError


class TestDeepSeekLLMProvider:
    """Test DeepSeekLLMProvider with mocked OpenAI-compatible client."""

    @pytest.fixture
    def provider(self):
        """Create DeepSeekLLMProvider with test API key."""
        os.environ["DEEPSEEK_API_KEY"] = "test-deepseek-api-key"
        return DeepSeekLLMProvider(api_key="test-deepseek-api-key")

    def test_provider_name_and_model(self, provider):
        """Provider identifies itself correctly."""
        assert provider.name == "deepseek"
        assert provider.model == "deepseek-chat"

    def test_provider_custom_model(self):
        """Provider accepts a custom model name."""
        os.environ["DEEPSEEK_API_KEY"] = "test-deepseek-api-key"
        provider = DeepSeekLLMProvider(api_key="test-deepseek-api-key", model="deepseek-coder")
        assert provider.model == "deepseek-coder"

    def test_missing_api_key_raises(self):
        """Missing API key raises PermanentProviderError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(PermanentProviderError) as exc_info:
                DeepSeekLLMProvider()
            assert "DEEPSEEK_API_KEY" in str(exc_info.value)

    def test_supports_json_mode(self, provider):
        """DeepSeek supports JSON response format."""
        assert provider.supports_json_mode() is True

    @pytest.mark.asyncio
    async def test_generate_returns_llm_response(self, provider):
        """Generate returns a valid LLMResponse."""
        mock_choice = MagicMock()
        mock_choice.message.content = '{"chapters": [{"title": "Intro"}]}'
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_client):
            result = await provider.generate("Analyze this text")

        assert isinstance(result, LLMResponse)
        assert result.text == '{"chapters": [{"title": "Intro"}]}'
        assert result.provider == "deepseek"
        assert result.model == "deepseek-chat"
        assert result.usage["prompt_tokens"] == 100
        assert result.usage["completion_tokens"] == 50

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, provider):
        """Generate includes system prompt in messages."""
        mock_choice = MagicMock()
        mock_choice.message.content = "Response with system context"
        mock_choice.message.role = "assistant"
        mock_choice.finish_reason = "stop"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 30
        mock_usage.total_tokens = 80

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_client):
            await provider.generate(
                "What is the weather?",
                system_prompt="You are a helpful weather assistant.",
            )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful weather assistant."
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "What is the weather?"

    @pytest.mark.asyncio
    async def test_generate_with_json_response_format(self, provider):
        """Generate sets JSON response format when requested."""
        mock_choice = MagicMock()
        mock_choice.message.content = '{"result": "ok"}'
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

        with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_client):
            await provider.generate("Return JSON", response_format="json")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"]["type"] == "json_object"

    @pytest.mark.asyncio
    async def test_generate_raises_transient_on_rate_limit(self, provider):
        """Rate limit raises TransientProviderError."""
        from openai import RateLimitError
        mock_error = RateLimitError(message="Rate limited", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_error

        with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_client):
            with pytest.raises(TransientProviderError):
                await provider.generate("test")

    @pytest.mark.asyncio
    async def test_generate_raises_permanent_on_auth_error(self, provider):
        """Authentication error raises PermanentProviderError."""
        from openai import AuthenticationError
        mock_error = AuthenticationError(message="Bad key", response=MagicMock(), body=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_error

        with patch("src.providers.llm.deepseek_llm.OpenAI", return_value=mock_client):
            with pytest.raises(PermanentProviderError):
                await provider.generate("test")
