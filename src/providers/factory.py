"""Factory functions for creating ASR and LLM provider instances."""

from typing import List, Optional

from src.providers.asr.assemblyai_asr import AssemblyAIASRProvider
from src.providers.asr.base import ASRProvider, ProviderCapabilities
from src.providers.asr.groq_asr import GroqASRProvider
from src.providers.asr.mlx_whisper_asr import MLXWhisperASR
from src.providers.asr.openai_asr import OpenAIASRProvider
from src.providers.llm.base import LLMProvider
from src.providers.llm.deepseek_llm import DeepSeekLLMProvider
from src.providers.llm.groq_llm import GroqLLMProvider
from src.providers.llm.openai_llm import OpenAILLMProvider
from src.utils.errors import CapabilityError


def create_asr_provider(
    provider_name: str,
    model: Optional[str] = None,
    required_features: Optional[List[str]] = None,
    **provider_kwargs,
) -> ASRProvider:
    """Create an ASR provider instance by name.

    Args:
        provider_name: Provider identifier (groq, assemblyai, openai).
        model: Optional model name override.
        required_features: Optional list of required feature names
            (e.g. ["word_timestamps"]). If provided, validates that
            the selected provider supports all requested features.
        **provider_kwargs: Additional keyword arguments to pass to provider constructor
            (e.g., request_delay_seconds, hf_token).

    Returns:
        Configured ASRProvider instance.

    Raises:
        ValueError: If provider_name is unknown.
        CapabilityError: If required_features are not supported.
    """
    from src.providers.asr.groq_asr import GroqASRProvider
    from src.providers.asr.assemblyai_asr import AssemblyAIASRProvider
    from src.providers.asr.openai_asr import OpenAIASRProvider
    from src.providers.asr.mlx_whisper_asr import MLXWhisperASR

    # Filter kwargs by provider type to avoid passing irrelevant parameters
    groq_kwargs = {k: v for k, v in provider_kwargs.items() if k in ['request_delay_seconds']}
    assemblyai_kwargs = {k: v for k, v in provider_kwargs.items() if k in ['request_delay_seconds']}
    openai_kwargs = {k: v for k, v in provider_kwargs.items() if k in ['request_delay_seconds']}
    mlx_kwargs = {k: v for k, v in provider_kwargs.items() if k in ['request_delay_seconds', 'hf_token']}

    # Map provider names to constructors with filtered kwargs
    provider_constructors = {
        "groq": lambda: GroqASRProvider(model=model, **groq_kwargs),
        "assemblyai": lambda: AssemblyAIASRProvider(model=model, **assemblyai_kwargs),
        "openai": lambda: OpenAIASRProvider(model=model, **openai_kwargs),
        "mlx": lambda: MLXWhisperASR(model=model, **mlx_kwargs),
        "mlx-whisper": lambda: MLXWhisperASR(model=model, **mlx_kwargs),
    }

    if provider_name not in provider_constructors:
        raise ValueError(
            f"Unknown ASR provider: {provider_name}. Valid: {list(provider_constructors.keys())}"
        )

    provider = provider_constructors[provider_name]()

    # Validate required features if specified
    if required_features:
        _validate_capabilities(provider, required_features)

    return provider


def _validate_capabilities(
    provider: ASRProvider, required_features: List[str]
) -> None:
    """Validate that a provider supports all required features.

    Args:
        provider: The ASR provider instance.
        required_features: List of feature names to check.

    Raises:
        CapabilityError: If any required feature is not supported.
    """
    caps = provider.capabilities
    missing = [f for f in required_features if not caps.supports_feature(f)]

    if missing:
        # Find providers that DO support the missing features
        all_providers = ["groq", "assemblyai", "openai", "mlx-whisper"]
        suggested = []
        for name in all_providers:
            if name == provider.name:
                continue
            try:
                p = create_asr_provider(name)
                if all(p.capabilities.supports_feature(f) for f in missing):
                    suggested.append(name)
            except Exception:
                pass

        raise CapabilityError(
            provider=provider.name,
            missing_feature=missing[0],
            suggested_providers=suggested,
        )


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
