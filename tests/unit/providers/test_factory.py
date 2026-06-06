"""Unit tests for provider factory functions."""

import pytest
from unittest.mock import patch

from src.providers.factory import create_asr_provider, create_llm_provider


class TestCreateASRProvider:
    """Test ASR provider factory."""

    @patch("src.providers.factory.GroqASRProvider")
    def test_create_groq_asr(self, mock_groq):
        """Creates GroqASRProvider with correct model."""
        mock_groq.return_value = "groq_instance"

        result = create_asr_provider("groq", model="whisper-large-v3")

        mock_groq.assert_called_once_with(model="whisper-large-v3")
        assert result == "groq_instance"

    @patch("src.providers.factory.GroqASRProvider")
    def test_create_groq_asr_no_model(self, mock_groq):
        """Creates GroqASRProvider with default model."""
        mock_groq.return_value = "groq_instance"

        result = create_asr_provider("groq")

        mock_groq.assert_called_once_with(model=None)

    @patch("src.providers.factory.AssemblyAIASRProvider")
    def test_create_assemblyai_asr(self, mock_assemblyai):
        """Creates AssemblyAIASRProvider."""
        mock_assemblyai.return_value = "assemblyai_instance"

        result = create_asr_provider("assemblyai")

        mock_assemblyai.assert_called_once()
        assert result == "assemblyai_instance"

    @patch("src.providers.factory.OpenAIASRProvider")
    def test_create_openai_asr(self, mock_openai):
        """Creates OpenAIASRProvider with correct model."""
        mock_openai.return_value = "openai_instance"

        result = create_asr_provider("openai", model="whisper-1")

        mock_openai.assert_called_once_with(model="whisper-1")
        assert result == "openai_instance"

    def test_create_unknown_asr_provider(self):
        """Raises ValueError for unknown ASR provider."""
        with pytest.raises(ValueError, match="Unknown ASR provider: unknown"):
            create_asr_provider("unknown")

    def test_create_unknown_asr_provider_lists_valid(self):
        """Error message lists valid providers."""
        with pytest.raises(ValueError) as exc_info:
            create_asr_provider("invalid")

        assert "groq" in str(exc_info.value)
        assert "assemblyai" in str(exc_info.value)
        assert "openai" in str(exc_info.value)


class TestCreateLLMProvider:
    """Test LLM provider factory."""

    @patch("src.providers.factory.DeepSeekLLMProvider")
    def test_create_deepseek_llm(self, mock_deepseek):
        """Creates DeepSeekLLMProvider with correct model."""
        mock_deepseek.return_value = "deepseek_instance"

        result = create_llm_provider("deepseek", model="deepseek-chat")

        mock_deepseek.assert_called_once_with(model="deepseek-chat")
        assert result == "deepseek_instance"

    @patch("src.providers.factory.DeepSeekLLMProvider")
    def test_create_deepseek_llm_no_model(self, mock_deepseek):
        """Creates DeepSeekLLMProvider with default model."""
        mock_deepseek.return_value = "deepseek_instance"

        result = create_llm_provider("deepseek")

        mock_deepseek.assert_called_once_with(model=None)

    @patch("src.providers.factory.GroqLLMProvider")
    def test_create_groq_llm(self, mock_groq):
        """Creates GroqLLMProvider with correct model."""
        mock_groq.return_value = "groq_llm_instance"

        result = create_llm_provider("groq", model="llama-3.1-70b")

        mock_groq.assert_called_once_with(model="llama-3.1-70b")
        assert result == "groq_llm_instance"

    @patch("src.providers.factory.OpenAILLMProvider")
    def test_create_openai_llm(self, mock_openai):
        """Creates OpenAILLMProvider with correct model."""
        mock_openai.return_value = "openai_llm_instance"

        result = create_llm_provider("openai", model="gpt-4o")

        mock_openai.assert_called_once_with(model="gpt-4o")
        assert result == "openai_llm_instance"

    def test_create_unknown_llm_provider(self):
        """Raises ValueError for unknown LLM provider."""
        with pytest.raises(ValueError, match="Unknown LLM provider: unknown"):
            create_llm_provider("unknown")

    def test_create_unknown_llm_provider_lists_valid(self):
        """Error message lists valid providers."""
        with pytest.raises(ValueError) as exc_info:
            create_llm_provider("invalid")

        assert "deepseek" in str(exc_info.value)
        assert "groq" in str(exc_info.value)
        assert "openai" in str(exc_info.value)
