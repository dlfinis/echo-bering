"""Provider factory for dynamic instantiation of ASR and LLM providers.

The factory handles provider selection based on configuration,
validates API keys, and maintains a registry for easy extension.
"""

from typing import Callable

from src.providers.asr.base import ASRProvider
from src.providers.asr.groq_asr import GroqASRProvider
from src.providers.asr.assemblyai_asr import AssemblyAIASRProvider
from src.providers.asr.openai_asr import OpenAIASRProvider
from src.providers.llm.base import LLMProvider
from src.providers.llm.deepseek_llm import DeepSeekLLMProvider
from src.providers.llm.groq_llm import GroqLLMProvider
from src.providers.llm.openai_llm import OpenAILLMProvider
from src.utils.errors import ConfigError, PermanentProviderError

# Type alias for provider constructors
ASRConstructor = Callable[..., ASRProvider]
LLMConstructor = Callable[..., LLMProvider]


class ProviderFactory:
    """Factory for creating ASR and LLM provider instances.

    Maintains a registry of provider constructors and handles
    API key validation before instantiation.
    """

    # ASR provider registry
    _asr_registry: dict[str, ASRConstructor] = {
        "groq": GroqASRProvider,
        "assemblyai": AssemblyAIASRProvider,
        "openai": OpenAIASRProvider,
    }

    # LLM provider registry
    _llm_registry: dict[str, LLMConstructor] = {
        "deepseek": DeepSeekLLMProvider,
        "groq": GroqLLMProvider,
        "openai": OpenAILLMProvider,
    }

    # API key environment variable mappings
    _asr_api_keys = {
        "groq": "GROQ_API_KEY",
        "assemblyai": "ASSEMBLYAI_API_KEY",
        "openai": "OPENAI_API_KEY",
    }

    _llm_api_keys = {
        "deepseek": "DEEPSEEK_API_KEY",
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
    }

    @classmethod
    def create_asr(cls, provider_name: str, **kwargs) -> ASRProvider:
        """Create an ASR provider by name.

        Args:
            provider_name: Provider identifier (e.g., 'groq', 'assemblyai', 'openai').
            **kwargs: Additional arguments passed to the provider constructor
                     (e.g., model, api_key).

        Returns:
            Configured ASRProvider instance.

        Raises:
            ConfigError: If provider is unknown or API key is missing.
        """
        if provider_name not in cls._asr_registry:
            available = ", ".join(cls._asr_registry.keys())
            raise ConfigError(
                f"Unknown ASR provider: '{provider_name}'. "
                f"Available providers: {available}"
            )

        # Validate API key
        env_key = cls._asr_api_keys.get(provider_name)
        if env_key and "api_key" not in kwargs:
            import os
            api_key = os.environ.get(env_key)
            if not api_key:
                raise ConfigError(
                    f"Missing API key for ASR provider '{provider_name}'. "
                    f"Set {env_key} environment variable or pass api_key."
                )
            kwargs["api_key"] = api_key

        try:
            constructor = cls._asr_registry[provider_name]
            return constructor(**kwargs)
        except PermanentProviderError as e:
            raise ConfigError(str(e)) from e

    @classmethod
    def create_llm(cls, provider_name: str, **kwargs) -> LLMProvider:
        """Create an LLM provider by name.

        Args:
            provider_name: Provider identifier (e.g., 'deepseek', 'groq', 'openai').
            **kwargs: Additional arguments passed to the provider constructor
                     (e.g., model, api_key).

        Returns:
            Configured LLMProvider instance.

        Raises:
            ConfigError: If provider is unknown or API key is missing.
        """
        if provider_name not in cls._llm_registry:
            available = ", ".join(cls._llm_registry.keys())
            raise ConfigError(
                f"Unknown LLM provider: '{provider_name}'. "
                f"Available providers: {available}"
            )

        # Validate API key
        env_key = cls._llm_api_keys.get(provider_name)
        if env_key and "api_key" not in kwargs:
            import os
            api_key = os.environ.get(env_key)
            if not api_key:
                raise ConfigError(
                    f"Missing API key for LLM provider '{provider_name}'. "
                    f"Set {env_key} environment variable or pass api_key."
                )
            kwargs["api_key"] = api_key

        try:
            constructor = cls._llm_registry[provider_name]
            return constructor(**kwargs)
        except PermanentProviderError as e:
            raise ConfigError(str(e)) from e

    @classmethod
    def list_asr_providers(cls) -> list[str]:
        """List registered ASR provider names."""
        return list(cls._asr_registry.keys())

    @classmethod
    def list_llm_providers(cls) -> list[str]:
        """List registered LLM provider names."""
        return list(cls._llm_registry.keys())

    @classmethod
    def register_asr(cls, name: str, constructor: ASRConstructor) -> None:
        """Register a custom ASR provider.

        Args:
            name: Provider identifier.
            constructor: Callable that returns an ASRProvider instance.
        """
        cls._asr_registry[name] = constructor

    @classmethod
    def register_llm(cls, name: str, constructor: LLMConstructor) -> None:
        """Register a custom LLM provider.

        Args:
            name: Provider identifier.
            constructor: Callable that returns an LLMProvider instance.
        """
        cls._llm_registry[name] = constructor
