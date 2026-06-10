"""Tests for provider capability detection and validation."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.providers.asr.base import (
    ProviderCapabilities,
    TranscriptResult,
    WordTimestamp,
)
from src.providers.asr.groq_asr import GroqASRProvider
from src.providers.asr.assemblyai_asr import AssemblyAIASRProvider
from src.providers.asr.openai_asr import OpenAIASRProvider
from src.providers.factory import create_asr_provider, _validate_capabilities
from src.utils.errors import CapabilityError


class TestProviderCapabilities:
    """Test ProviderCapabilities dataclass."""

    def test_default_capabilities_are_false(self):
        """Default capabilities are all disabled."""
        caps = ProviderCapabilities()
        assert caps.has_word_timestamps is False
        assert caps.has_speaker_diarization is False
        assert caps.has_utterances is False
        assert caps.max_duration_s == 0.0

    def test_supports_feature_word_timestamps(self):
        """supports_feature returns correct value for word_timestamps."""
        caps = ProviderCapabilities(has_word_timestamps=True)
        assert caps.supports_feature("word_timestamps") is True
        assert caps.supports_feature("speaker_diarization") is False

    def test_supports_feature_unknown_returns_false(self):
        """Unknown feature names return False."""
        caps = ProviderCapabilities(has_word_timestamps=True)
        assert caps.supports_feature("unknown_feature") is False

    def test_supports_all_features(self):
        """All features can be enabled simultaneously."""
        caps = ProviderCapabilities(
            has_word_timestamps=True,
            has_speaker_diarization=True,
            has_utterances=True,
            max_duration_s=300.0,
        )
        assert caps.supports_feature("word_timestamps") is True
        assert caps.supports_feature("speaker_diarization") is True
        assert caps.supports_feature("utterances") is True
        assert caps.max_duration_s == 300.0

    def test_frozen_dataclass(self):
        """Capabilities is immutable."""
        caps = ProviderCapabilities(has_word_timestamps=True)
        with pytest.raises(Exception):  # FrozenInstanceError
            caps.has_word_timestamps = False


class TestGroqCapabilities:
    """Test Groq ASR provider capability detection."""

    @pytest.fixture
    def provider(self):
        os.environ["GROQ_API_KEY"] = "test-key"
        return GroqASRProvider(api_key="test-key")

    def test_groq_has_no_word_timestamps(self, provider):
        """Groq does not provide word-level timestamps."""
        assert provider.capabilities.has_word_timestamps is False

    def test_groq_has_no_diarization(self, provider):
        """Groq does not support speaker diarization."""
        assert provider.capabilities.has_speaker_diarization is False

    def test_groq_has_no_utterances(self, provider):
        """Groq does not provide utterance segmentation."""
        assert provider.capabilities.has_utterances is False

    def test_groq_capabilities_is_stable(self, provider):
        """Multiple calls return the same capabilities object."""
        caps1 = provider.capabilities
        caps2 = provider.capabilities
        assert caps1 is caps2


class TestAssemblyAICapabilities:
    """Test AssemblyAI provider capability detection."""

    @pytest.fixture
    def provider(self):
        os.environ["ASSEMBLYAI_API_KEY"] = "test-key"
        return AssemblyAIASRProvider(api_key="test-key")

    def test_assemblyai_has_word_timestamps(self, provider):
        """AssemblyAI provides word-level timestamps."""
        assert provider.capabilities.has_word_timestamps is True

    def test_assemblyai_has_diarization(self, provider):
        """AssemblyAI supports speaker diarization."""
        assert provider.capabilities.has_speaker_diarization is True

    def test_assemblyai_has_no_utterances(self, provider):
        """AssemblyAI does not provide utterance segmentation by default."""
        assert provider.capabilities.has_utterances is False

    def test_assemblyai_capabilities_is_stable(self, provider):
        """Multiple calls return the same capabilities object."""
        caps1 = provider.capabilities
        caps2 = provider.capabilities
        assert caps1 is caps2


class TestOpenAICapabilities:
    """Test OpenAI ASR provider capability detection."""

    @pytest.fixture
    def provider(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        return OpenAIASRProvider(api_key="test-key")

    def test_openai_has_no_word_timestamps(self, provider):
        """OpenAI basic API does not provide word-level timestamps."""
        assert provider.capabilities.has_word_timestamps is False

    def test_openai_has_no_diarization(self, provider):
        """OpenAI basic API does not support speaker diarization."""
        assert provider.capabilities.has_speaker_diarization is False

    def test_openai_has_no_utterances(self, provider):
        """OpenAI basic API does not provide utterance segmentation."""
        assert provider.capabilities.has_utterances is False


class TestCapabilityValidation:
    """Test capability validation in the factory."""

    def test_validate_passes_when_supported(self):
        """Validation passes when provider supports the feature."""
        provider = AssemblyAIASRProvider(api_key="test-key")
        # Should not raise
        _validate_capabilities(provider, ["word_timestamps"])

    def test_validate_raises_when_unsupported(self):
        """Validation raises CapabilityError for unsupported features."""
        provider = GroqASRProvider(api_key="test-key")
        with pytest.raises(CapabilityError) as exc_info:
            _validate_capabilities(provider, ["word_timestamps"])
        assert exc_info.value.provider == "groq"
        assert exc_info.value.missing_feature == "word_timestamps"
        assert "assemblyai" in exc_info.value.suggested_providers

    def test_create_asr_provider_with_required_features_passes(self):
        """Factory creates provider when features are supported."""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"}):
            provider = create_asr_provider(
                "assemblyai", required_features=["word_timestamps"]
            )
            assert provider.name == "assemblyai"

    def test_create_asr_provider_with_required_features_fails(self):
        """Factory raises CapabilityError when features not supported."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            with pytest.raises(CapabilityError):
                create_asr_provider("groq", required_features=["word_timestamps"])

    def test_create_asr_provider_without_features_works(self):
        """Factory works normally when no features required."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = create_asr_provider("groq")
            assert provider.name == "groq"

    def test_create_asr_provider_unknown_provider(self):
        """Factory raises ValueError for unknown provider."""
        with pytest.raises(ValueError):
            create_asr_provider("unknown-provider")


class TestTranscriptResultUtilityMethods:
    """Test TranscriptResult utility methods for capability-aware access."""

    def test_has_word_timestamps_true(self):
        """has_word_timestamps returns True when words exist."""
        result = TranscriptResult(
            text="Hello world",
            confidence=0.9,
            words=[WordTimestamp(word="Hello", start=0.0, end=0.5)],
            duration_s=1.0,
            provider="test",
            model="test",
        )
        assert result.has_word_timestamps() is True

    def test_has_word_timestamps_false(self):
        """has_word_timestamps returns False when no words."""
        result = TranscriptResult(
            text="Hello world",
            confidence=0.9,
            words=[],
            duration_s=1.0,
            provider="test",
            model="test",
        )
        assert result.has_word_timestamps() is False

    def test_get_word_at_time_returns_match(self):
        """get_word_at_time finds the correct word."""
        result = TranscriptResult(
            text="Hello world",
            confidence=0.9,
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5),
                WordTimestamp(word="world", start=0.5, end=1.0),
            ],
            duration_s=1.0,
            provider="test",
            model="test",
        )
        word = result.get_word_at_time(0.3)
        assert word is not None
        assert word.word == "Hello"

    def test_get_word_at_time_returns_none_outside_range(self):
        """get_word_at_time returns None for time outside all words."""
        result = TranscriptResult(
            text="Hello",
            confidence=0.9,
            words=[WordTimestamp(word="Hello", start=0.0, end=1.0)],
            duration_s=1.0,
            provider="test",
            model="test",
        )
        assert result.get_word_at_time(5.0) is None

    def test_get_word_at_time_no_words(self):
        """get_word_at_time returns None when no words available."""
        result = TranscriptResult(
            text="Hello",
            confidence=0.9,
            words=[],
            duration_s=1.0,
            provider="test",
            model="test",
        )
        assert result.get_word_at_time(0.5) is None

    def test_get_duration_per_word(self):
        """get_duration_per_word calculates average correctly."""
        result = TranscriptResult(
            text="one two three four five",
            confidence=0.9,
            words=[
                WordTimestamp(word=w, start=float(i), end=float(i + 1))
                for i, w in enumerate(["one", "two", "three", "four", "five"])
            ],
            duration_s=5.0,
            provider="test",
            model="test",
        )
        assert result.get_duration_per_word() == 1.0

    def test_get_duration_per_word_no_words(self):
        """get_duration_per_word returns 0.0 when no words."""
        result = TranscriptResult(
            text="Hello",
            confidence=0.9,
            words=[],
            duration_s=1.0,
            provider="test",
            model="test",
        )
        assert result.get_duration_per_word() == 0.0

    def test_get_duration_per_word_zero_duration(self):
        """get_duration_per_word returns 0.0 when duration is zero."""
        result = TranscriptResult(
            text="Hello",
            confidence=0.9,
            words=[WordTimestamp(word="Hello", start=0.0, end=0.5)],
            duration_s=0.0,
            provider="test",
            model="test",
        )
        assert result.get_duration_per_word() == 0.0


class TestBackwardCompatibility:
    """Test that existing code continues to work with the changes."""

    def test_transcript_result_words_defaults_to_empty_list(self):
        """words field defaults to empty list when not provided."""
        # This is critical: existing code that doesn't pass words should work
        result = TranscriptResult(
            text="Hello",
            confidence=1.0,
            provider="test",
            model="test",
        )
        assert result.words == []

    def test_transcript_result_duration_defaults_to_zero(self):
        """duration_s field defaults to 0.0 when not provided."""
        result = TranscriptResult(
            text="Hello",
            confidence=1.0,
            provider="test",
            model="test",
        )
        assert result.duration_s == 0.0

    def test_transcript_result_with_words_still_works(self):
        """Providing words explicitly still works."""
        result = TranscriptResult(
            text="Hello world",
            confidence=0.9,
            words=[WordTimestamp(word="Hello", start=0.0, end=0.5)],
            duration_s=1.0,
            provider="test",
            model="test",
        )
        assert len(result.words) == 1
        assert result.words[0].word == "Hello"
