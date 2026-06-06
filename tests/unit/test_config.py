"""Tests for configuration model and loader in src.config."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from src.config import Config, ConfigError, load_config


class TestConfigModel:
    """Test Config Pydantic model validation."""

    def test_valid_config_creation(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config = Config(
            asr_provider="groq",
            llm_provider="deepseek",
            input_video=video,
        )
        assert config.asr_provider == "groq"
        assert config.llm_provider == "deepseek"
        assert config.output_dir == Path("./output")
        assert config.language == "es"
        assert config.cut_mode == "fast"
        assert config.max_budget_usd == 2.0

    def test_invalid_asr_provider(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        with pytest.raises(ValueError):
            Config(asr_provider="unknown_provider", llm_provider="deepseek", input_video=video)

    def test_invalid_llm_provider(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        with pytest.raises(ValueError):
            Config(asr_provider="groq", llm_provider="unknown_provider", input_video=video)

    def test_missing_input_video(self):
        with pytest.raises(ValueError):
            Config(
                asr_provider="groq",
                llm_provider="deepseek",
                input_video=Path("/nonexistent/video.mp4"),
            )

    def test_max_budget_must_be_positive(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        with pytest.raises(ValueError):
            Config(asr_provider="groq", llm_provider="deepseek", input_video=video, max_budget_usd=0)
        with pytest.raises(ValueError):
            Config(asr_provider="groq", llm_provider="deepseek", input_video=video, max_budget_usd=-1.0)

    def test_custom_output_dir(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        custom_out = tmp_path / "custom_output"
        config = Config(
            asr_provider="groq",
            llm_provider="deepseek",
            input_video=video,
            output_dir=custom_out,
        )
        assert config.output_dir == custom_out

    def test_confidence_threshold_bounds(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        with pytest.raises(ValueError):
            Config(asr_provider="groq", llm_provider="deepseek", input_video=video,
                   segmentation_confidence_threshold=1.5)
        with pytest.raises(ValueError):
            Config(asr_provider="groq", llm_provider="deepseek", input_video=video,
                   segmentation_confidence_threshold=-0.1)

    def test_chunk_overlap_less_than_60(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        with pytest.raises(ValueError):
            Config(asr_provider="groq", llm_provider="deepseek", input_video=video,
                   chunk_overlap_seconds=60)

    def test_cut_mode_values(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        Config(asr_provider="groq", llm_provider="deepseek", input_video=video, cut_mode="fast")
        Config(asr_provider="groq", llm_provider="deepseek", input_video=video, cut_mode="precise")
        with pytest.raises(ValueError):
            Config(asr_provider="groq", llm_provider="deepseek", input_video=video, cut_mode="invalid")

    def test_generate_flags_defaults(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config = Config(asr_provider="groq", llm_provider="deepseek", input_video=video)
        assert config.generate_subtitles is True
        assert config.generate_summaries is True
        assert config.generate_highlights is True
        assert config.generate_index is False


class TestLoadConfig:
    """Test YAML + .env config loading."""

    def _write_yaml(self, tmp_path: Path, data: dict) -> Path:
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(data))
        return config_path

    def test_load_from_yaml_file(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
        })
        config = load_config(config_path)
        assert config.asr_provider == "groq"
        assert config.llm_provider == "deepseek"

    def test_env_override_yaml(self, tmp_path, monkeypatch):
        """Environment variables override YAML values."""
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "max_budget_usd": 1.0,
        })
        # Override max_budget via env
        monkeypatch.setenv("MAX_BUDGET_USD", "10.0")
        config = load_config(config_path)
        assert config.max_budget_usd == 10.0

    def test_env_override_provider(self, tmp_path, monkeypatch):
        """Env can override provider selection."""
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
        })
        monkeypatch.setenv("ASR_PROVIDER", "openai")
        config = load_config(config_path)
        assert config.asr_provider == "openai"

    def test_invalid_provider_from_yaml_raises(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "invalid_provider",
            "llm_provider": "deepseek",
            "input_video": str(video),
        })
        with pytest.raises(ConfigError):
            load_config(config_path)

    def test_missing_required_field_raises(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "groq",
            # llm_provider missing
            "input_video": str(video),
        })
        with pytest.raises(ConfigError):
            load_config(config_path)

    def test_nonexistent_yaml_raises(self):
        with pytest.raises(ConfigError):
            load_config(Path("/nonexistent/config.yaml"))

    def test_output_dir_auto_created(self, tmp_path):
        output_dir = tmp_path / "new_output"
        assert not output_dir.exists()
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "output_dir": str(output_dir),
        })
        config = load_config(config_path)
        assert output_dir.exists()

    def test_required_asr_features_defaults_to_empty(self, tmp_path):
        """required_asr_features defaults to empty list."""
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "groq",
            "llm_provider": "deepseek",
            "input_video": str(video),
        })
        config = load_config(config_path)
        assert config.required_asr_features == []

    def test_required_asr_features_from_yaml(self, tmp_path):
        """required_asr_features can be set in YAML."""
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "assemblyai",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "required_asr_features": ["word_timestamps"],
        })
        config = load_config(config_path)
        assert config.required_asr_features == ["word_timestamps"]

    def test_required_asr_features_multiple(self, tmp_path):
        """Multiple required features can be specified."""
        video = tmp_path / "test.mp4"
        video.write_text("fake")
        config_path = self._write_yaml(tmp_path, {
            "asr_provider": "assemblyai",
            "llm_provider": "deepseek",
            "input_video": str(video),
            "required_asr_features": ["word_timestamps", "speaker_diarization"],
        })
        config = load_config(config_path)
        assert len(config.required_asr_features) == 2
        assert "word_timestamps" in config.required_asr_features
        assert "speaker_diarization" in config.required_asr_features
