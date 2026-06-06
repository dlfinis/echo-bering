"""Tests for ProviderFactory implementation."""

import os
from unittest.mock import patch

import pytest

from src.factories.provider_factory import ProviderFactory
from src.providers.asr.base import ASRProvider
from src.providers.asr.groq_asr import GroqASRProvider
from src.providers.asr.assemblyai_asr import AssemblyAIASRProvider
from src.providers.asr.openai_asr import OpenAIASRProvider
from src.providers.llm.base import LLMProvider
from src.providers.llm.deepseek_llm import DeepSeekLLMProvider
from src.providers.llm.groq_llm import GroqLLMProvider
from src.providers.llm.openai_llm import OpenAILLMProvider
from src.utils.errors import ConfigError, PermanentProviderError


class TestProviderFactoryPermanentProviderError:
    """Test error handling for PermanentProviderError during construction."""

    def test_create_asr_permanent_error_wrapped(self):
        """PermanentProviderError during ASR creation is wrapped as ConfigError."""
        class FailingASR(ASRProvider):
            def __init__(self, **kwargs):
                raise PermanentProviderError("Init failed")

            async def transcribe(self, audio_path: str):
                raise NotImplementedError

            async def supports_file(self, audio_path: str) -> bool:
                return False

        ProviderFactory.register_asr("failing_asr", lambda **kwargs: FailingASR(**kwargs))

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with pytest.raises(ConfigError) as exc_info:
                ProviderFactory.create_asr("failing_asr")
            assert "Init failed" in str(exc_info.value)

    def test_create_llm_permanent_error_wrapped(self):
        """PermanentProviderError during LLM creation is wrapped as ConfigError."""
        class FailingLLM(LLMProvider):
            def __init__(self, **kwargs):
                raise PermanentProviderError("LLM init failed")

            async def generate(self, prompt: str, system_prompt=None, response_format=None):
                raise NotImplementedError

            def supports_json_mode(self) -> bool:
                return False

        ProviderFactory.register_llm("failing_llm", lambda **kwargs: FailingLLM(**kwargs))

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            with pytest.raises(ConfigError) as exc_info:
                ProviderFactory.create_llm("failing_llm")
            assert "LLM init failed" in str(exc_info.value)


class TestProviderFactoryCreateASR:
    """Test ASR provider creation via factory."""

    def test_create_groq_asr(self):
        """Factory creates GroqASRProvider for 'groq'."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("groq")
        assert isinstance(provider, GroqASRProvider)
        assert provider.name == "groq"

    def test_create_assemblyai_asr(self):
        """Factory creates AssemblyAIASRProvider for 'assemblyai'."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("assemblyai")
        assert isinstance(provider, AssemblyAIASRProvider)
        assert provider.name == "assemblyai"

    def test_create_openai_asr(self):
        """Factory creates OpenAIASRProvider for 'openai'."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("openai")
        assert isinstance(provider, OpenAIASRProvider)
        assert provider.name == "openai"

    def test_create_asr_with_custom_model(self):
        """Factory passes custom model to provider."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("groq", model="whisper-large-v3")
        assert provider.model == "whisper-large-v3"

    def test_create_asr_unknown_provider_raises(self):
        """Unknown ASR provider raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            ProviderFactory.create_asr("unknown_asr")
        assert "Unknown ASR provider" in str(exc_info.value)

    def test_create_asr_missing_api_key_raises(self):
        """Missing API key raises ConfigError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                ProviderFactory.create_asr("groq")
            assert "GROQ_API_KEY" in str(exc_info.value)


class TestProviderFactoryCreateLLM:
    """Test LLM provider creation via factory."""

    def test_create_deepseek_llm(self):
        """Factory creates DeepSeekLLMProvider for 'deepseek'."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            provider = ProviderFactory.create_llm("deepseek")
        assert isinstance(provider, DeepSeekLLMProvider)
        assert provider.name == "deepseek"

    def test_create_groq_llm(self):
        """Factory creates GroqLLMProvider for 'groq'."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = ProviderFactory.create_llm("groq")
        assert isinstance(provider, GroqLLMProvider)
        assert provider.name == "groq"

    def test_create_openai_llm(self):
        """Factory creates OpenAILLMProvider for 'openai'."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            provider = ProviderFactory.create_llm("openai")
        assert isinstance(provider, OpenAILLMProvider)
        assert provider.name == "openai"

    def test_create_llm_with_custom_model(self):
        """Factory passes custom model to provider."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            provider = ProviderFactory.create_llm("deepseek", model="deepseek-coder")
        assert provider.model == "deepseek-coder"

    def test_create_llm_unknown_provider_raises(self):
        """Unknown LLM provider raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            ProviderFactory.create_llm("unknown_llm")
        assert "Unknown LLM provider" in str(exc_info.value)

    def test_create_llm_missing_api_key_raises(self):
        """Missing API key raises ConfigError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigError) as exc_info:
                ProviderFactory.create_llm("deepseek")
            assert "DEEPSEEK_API_KEY" in str(exc_info.value)


class TestProviderFactoryRegistry:
    """Test provider registry."""

    def test_list_asr_providers(self):
        """Factory lists available ASR providers."""
        providers = ProviderFactory.list_asr_providers()
        assert "groq" in providers
        assert "assemblyai" in providers
        assert "openai" in providers

    def test_list_llm_providers(self):
        """Factory lists available LLM providers."""
        providers = ProviderFactory.list_llm_providers()
        assert "deepseek" in providers
        assert "groq" in providers
        assert "openai" in providers

    def test_register_custom_asr_provider(self):
        """Factory allows registering custom ASR providers."""
        class CustomASR(ASRProvider):
            async def transcribe(self, audio_path: str):
                raise NotImplementedError

            async def supports_file(self, audio_path: str) -> bool:
                return False

        ProviderFactory.register_asr("custom", lambda **kwargs: CustomASR())
        providers = ProviderFactory.list_asr_providers()
        assert "custom" in providers

    def test_register_custom_llm_provider(self):
        """Factory allows registering custom LLM providers."""
        class CustomLLM(LLMProvider):
            async def generate(self, prompt: str, system_prompt=None, response_format=None):
                raise NotImplementedError

            def supports_json_mode(self) -> bool:
                return False

        ProviderFactory.register_llm("custom_llm", lambda **kwargs: CustomLLM())
        providers = ProviderFactory.list_llm_providers()
        assert "custom_llm" in providers
