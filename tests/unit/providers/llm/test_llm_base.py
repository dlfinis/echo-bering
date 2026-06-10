"""Tests for LLM provider base classes and domain models."""

import pytest

from src.providers.llm.base import LLMProvider, LLMResponse


class TestLLMResponse:
    """Test LLMResponse Pydantic model."""

    def test_valid_llm_response_creation(self):
        """LLMResponse can be created with required fields."""
        response = LLMResponse(
            text="Hello, world!",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            provider="deepseek",
            model="deepseek-chat-v4-flash",
        )
        assert response.text == "Hello, world!"
        assert response.provider == "deepseek"
        assert response.model == "deepseek-chat-v4-flash"
        assert response.usage["total_tokens"] == 15

    def test_llm_response_with_confidence(self):
        """LLMResponse supports optional confidence field."""
        response = LLMResponse(
            text="Parsed JSON result",
            usage={"prompt_tokens": 20, "completion_tokens": 50, "total_tokens": 70},
            provider="groq",
            model="llama-4-scorpion",
            confidence=0.92,
        )
        assert response.confidence == 0.92

    def test_llm_response_default_confidence(self):
        """LLMResponse defaults confidence to 1.0."""
        response = LLMResponse(
            text="Default confidence test",
            usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            provider="openai",
            model="gpt-4o-mini",
        )
        assert response.confidence == 1.0

    def test_llm_response_with_finish_reason(self):
        """LLMResponse supports optional finish_reason field."""
        response = LLMResponse(
            text="Stopped at max tokens",
            usage={"prompt_tokens": 100, "completion_tokens": 4096, "total_tokens": 4196},
            provider="openai",
            model="gpt-4o-mini",
            finish_reason="length",
        )
        assert response.finish_reason == "length"

    def test_llm_response_confidence_bounds(self):
        """LLMResponse validates confidence between 0 and 1."""
        # Valid values
        LLMResponse(
            text="Min confidence",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            provider="test",
            model="test",
            confidence=0.0,
        )
        LLMResponse(
            text="Max confidence",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            provider="test",
            model="test",
            confidence=1.0,
        )


class TestLLMProvider:
    """Test LLMProvider abstract interface."""

    def test_llm_provider_is_abstract(self):
        """LLMProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            LLMProvider()

    def test_concrete_implementation_must_implement_generate(self):
        """Concrete LLM providers must implement generate method."""

        class IncompleteProvider(LLMProvider):
            def supports_json_mode(self) -> bool:
                return False

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_concrete_implementation_must_implement_supports_json_mode(self):
        """Concrete LLM providers must implement supports_json_mode."""

        class IncompleteProvider(LLMProvider):
            async def generate(
                self,
                prompt: str,
                system_prompt: str | None = None,
                response_format: str | None = None,
            ) -> LLMResponse:
                raise NotImplementedError

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_minimal_concrete_provider(self):
        """A minimal concrete provider can be instantiated."""

        class DummyProvider(LLMProvider):
            async def generate(
                self,
                prompt: str,
                system_prompt: str | None = None,
                response_format: str | None = None,
            ) -> LLMResponse:
                return LLMResponse(
                    text="dummy",
                    usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    provider="dummy",
                    model="dummy",
                )

            def supports_json_mode(self) -> bool:
                return False

        provider = DummyProvider()
        assert provider is not None
