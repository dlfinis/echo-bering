"""Factory functions for creating ASR and LLM provider instances."""

from typing import Optional

from src.providers.asr.assemblyai_asr import AssemblyAIASRProvider
from src.providers.asr.base import ASRProvider
from src.providers.asr.groq_asr import GroqASRProvider
from src.providers.asr.openai_asr import OpenAIASRProvider
from src.providers.llm.base import LLMProvider
from src.providers.llm.deepseek_llm import DeepSeekLLMProvider
from src.providers.llm.groq_llm import GroqLLMProvider
from src.providers.llm.openai_llm import OpenAILLMProvider


def create_asr_provider(provider_name: str, model: Optional[str] = None) -> ASRProvider:
    """Create an ASR provider instance by name.

    Args:
        provider_name: Provider identifier (groq, assemblyai, openai).
        model: Optional model name override.

    Returns:
        ASRProvider instance.

    Raises:
        ValueError: If provider name is not recognized.
    """
    providers = {
        "groq": lambda: GroqASRProvider(model=model),
        "assemblyai": lambda: AssemblyAIASRProvider(),
        "openai": lambda: OpenAIASRProvider(model=model),
    }

    if provider_name not in providers:
        raise ValueError(f"Unknown ASR provider: {provider_name}. Valid: {list(providers.keys())}")

    return providers[provider_name]()


def create_llm_provider(provider_name: str, model: Optional[str] = None) -> LLMProvider:
    """Create an LLM provider instance by name.

    Args:
        provider_name: Provider identifier (deepseek, groq, openai).
        model: Optional model name override.

    Returns:
        LLMProvider instance.

    Raises:
        ValueError: If provider name is not recognized.
    """
    providers = {
        "deepseek": lambda: DeepSeekLLMProvider(model=model),
        "groq": lambda: GroqLLMProvider(model=model),
        "openai": lambda: OpenAILLMProvider(model=model),
    }

    if provider_name not in providers:
        raise ValueError(f"Unknown LLM provider: {provider_name}. Valid: {list(providers.keys())}")

    return providers[provider_name]()
