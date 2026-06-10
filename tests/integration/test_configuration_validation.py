"""Integration tests for configuration validation.

Tests all configuration combinations, provider-specific options,
environment variable vs YAML precedence, and edge cases.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.config import Config, load_config
from src.factories.provider_factory import ProviderFactory
from src.utils.errors import ConfigError


class TestAllProviderCombinations:
    """Test all valid ASR x LLM provider combinations."""

    @pytest.fixture
    def valid_input_video(self, tmp_path):
        """Create a fake input video file."""
        video = tmp_path / "test.mp4"
        video.touch()
        return video

    @pytest.fixture
    def output_dir(self, tmp_path):
        """Create an output directory."""
        d = tmp_path / "output"
        d.mkdir()
        return d

    def _create_config_yaml(self, tmp_path, asr, llm, **overrides):
        """Create a YAML config file with given providers."""
        config_data = {
            "asr_provider": asr,
            "llm_provider": llm,
            "input_video": str(tmp_path / "test.mp4"),
            "output_dir": str(tmp_path / "output"),
        }
        config_data.update(overrides)

        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)
        return config_path

    @pytest.mark.parametrize("asr,llm", [
        ("groq", "deepseek"),
        ("groq", "groq"),
        ("groq", "openai"),
        ("assemblyai", "deepseek"),
        ("assemblyai", "groq"),
        ("assemblyai", "openai"),
        ("openai", "deepseek"),
        ("openai", "groq"),
        ("openai", "openai"),
    ])
    def test_all_provider_combinations_valid(self, tmp_path, asr, llm):
        """All 9 ASR x LLM combinations are valid in config."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": asr,
            "llm_provider": llm,
            "input_video": str(video),
            "output_dir": str(output),
        }

        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-groq-key",
            "DEEPSEEK_API_KEY": "test-deepseek-key",
            "OPENAI_API_KEY": "test-openai-key",
            "ASSEMBLYAI_API_KEY": "test-assemblyai-key",
        }):
            config = load_config(config_path)

        assert config.asr_provider == asr
        assert config.llm_provider == llm

    def test_factory_creates_all_asr_providers(self):
        """Factory can create all registered ASR providers."""
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-key",
            "OPENAI_API_KEY": "test-key",
            "ASSEMBLYAI_API_KEY": "test-key",
        }):
            groq = ProviderFactory.create_asr("groq")
            assemblyai = ProviderFactory.create_asr("assemblyai")
            openai = ProviderFactory.create_asr("openai")

        assert groq.name == "groq"
        assert assemblyai.name == "assemblyai"
        assert openai.name == "openai"

    def test_factory_creates_all_llm_providers(self):
        """Factory can create all registered LLM providers."""
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-key",
            "OPENAI_API_KEY": "test-key",
            "DEEPSEEK_API_KEY": "test-key",
        }):
            deepseek = ProviderFactory.create_llm("deepseek")
            groq = ProviderFactory.create_llm("groq")
            openai = ProviderFactory.create_llm("openai")

        assert deepseek.name == "deepseek"
        assert groq.name == "groq"
        assert openai.name == "openai"


class TestEnvironmentVariablePrecedence:
    """Test environment variable vs YAML configuration precedence."""

    def test_env_overrides_yaml_asr_provider(self, tmp_path):
        """ASR_PROVIDER env var overrides YAML value."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "output_dir": str(output),
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with patch.dict(os.environ, {
            "ASR_PROVIDER": "assemblyai",
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "test-key",
            "ASSEMBLYAI_API_KEY": "test-key",
        }):
            config = load_config(config_path)

        assert config.asr_provider == "assemblyai"  # env overrides YAML

    def test_env_overrides_yaml_llm_provider(self, tmp_path):
        """LLM_PROVIDER env var overrides YAML value."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "output_dir": str(output),
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-key",
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-key",
        }):
            config = load_config(config_path)

        assert config.llm_provider == "openai"  # env overrides YAML

    def test_env_overrides_yaml_budget(self, tmp_path):
        """MAX_BUDGET_USD env var overrides YAML value."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "output_dir": str(output),
            "max_budget_usd": 5.0,
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-key",
            "DEEPSEEK_API_KEY": "test-key",
            "MAX_BUDGET_USD": "15.0",
        }):
            config = load_config(config_path)

        assert config.max_budget_usd == 15.0  # env overrides YAML

    def test_yaml_value_used_when_no_env_override(self, tmp_path):
        """YAML values are used when no env var is set."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": "assemblyai",
            "llm_provider": "groq",
            "input_video": str(video),
            "output_dir": str(output),
            "max_budget_usd": 3.5,
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with patch.dict(os.environ, {
            "ASSEMBLYAI_API_KEY": "test-key",
            "GROQ_API_KEY": "test-key",
        }):
            config = load_config(config_path)

        assert config.asr_provider == "assemblyai"
        assert config.llm_provider == "groq"
        assert config.max_budget_usd == 3.5


class TestProviderSpecificConfiguration:
    """Test provider-specific configuration options."""

    def test_asr_model_passed_to_provider(self):
        """ASR model config is passed to provider constructor."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            provider = ProviderFactory.create_asr("groq", model="whisper-large-v3")
        assert provider.model == "whisper-large-v3"

    def test_llm_model_passed_to_provider(self):
        """LLM model config is passed to provider constructor."""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            provider = ProviderFactory.create_llm("deepseek", model="deepseek-coder")
        assert provider.model == "deepseek-coder"

    def test_default_models_used_when_not_specified(self):
        """Default models are used when model config is not specified."""
        with patch.dict(os.environ, {
            "GROQ_API_KEY": "test-key",
            "DEEPSEEK_API_KEY": "test-key",
            "OPENAI_API_KEY": "test-key",
            "ASSEMBLYAI_API_KEY": "test-key",
        }):
            groq_asr = ProviderFactory.create_asr("groq")
            assemblyai_asr = ProviderFactory.create_asr("assemblyai")
            openai_asr = ProviderFactory.create_asr("openai")
            deepseek_llm = ProviderFactory.create_llm("deepseek")
            groq_llm = ProviderFactory.create_llm("groq")
            openai_llm = ProviderFactory.create_llm("openai")

        assert groq_asr.model == "whisper-large-v3-turbo"
        assert assemblyai_asr.model == "assemblyai-default"
        assert openai_asr.model == "whisper-1"
        assert deepseek_llm.model == "deepseek-chat"
        assert groq_llm.model == "llama-3.3-70b-versatile"
        assert openai_llm.model == "gpt-4o-mini"


class TestConfigurationEdgeCases:
    """Test configuration edge cases."""

    def test_invalid_asr_provider_rejected(self, tmp_path):
        """Invalid ASR provider name is rejected by config validation."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": "invalid_provider",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "output_dir": str(output),
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ConfigError):
            load_config(config_path)

    def test_invalid_llm_provider_rejected(self, tmp_path):
        """Invalid LLM provider name is rejected by config validation."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": "groq",
            "llm_provider": "invalid_llm",
            "input_video": str(video),
            "output_dir": str(output),
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ConfigError):
            load_config(config_path)

    def test_missing_api_key_for_selected_provider(self):
        """Missing API key for selected provider raises ConfigError when creating provider."""
        # Clear all API keys and only set GROQ_API_KEY
        original_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ["GROQ_API_KEY"] = "test-key"

            # Factory validates API keys when creating providers
            with pytest.raises(ConfigError) as exc_info:
                ProviderFactory.create_llm("deepseek")
            assert "DEEPSEEK_API_KEY" in str(exc_info.value)
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_config_file_not_found_raises(self):
        """Missing config file raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            load_config(Path("/nonexistent/config.yaml"))
        assert "not found" in str(exc_info.value)

    def test_invalid_yaml_raises_config_error(self, tmp_path):
        """Invalid YAML syntax raises ConfigError."""
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            f.write("invalid: yaml: syntax: [")

        with pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "Invalid YAML" in str(exc_info.value)

    def test_budget_must_be_positive(self, tmp_path):
        """Negative budget is rejected by validation."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "output_dir": str(output),
            "max_budget_usd": -1.0,
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ConfigError):
            load_config(config_path)

    def test_chunk_duration_must_be_positive(self, tmp_path):
        """Zero or negative chunk duration is rejected."""
        video = tmp_path / "test.mp4"
        video.touch()
        output = tmp_path / "output"
        output.mkdir()

        config_data = {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "output_dir": str(output),
            "chunk_duration_minutes": 0,
        }
        config_path = tmp_path / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ConfigError):
            load_config(config_path)
