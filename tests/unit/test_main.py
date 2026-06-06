"""Unit tests for CLI entry point."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import (
    cli,
    find_config,
    load_and_validate_config,
    setup_progress_display,
    setup_orchestrator,
)
from src.utils.errors import ConfigError


class TestFindConfig:
    """Test config file discovery."""

    def test_find_config_explicit_path(self, tmp_path):
        """Returns explicit path if file exists."""
        config_file = tmp_path / "config.yaml"
        config_file.touch()

        result = find_config(str(config_file))

        assert result == config_file

    def test_find_config_explicit_path_not_found(self, tmp_path):
        """Raises ConfigError for nonexistent explicit path."""
        nonexistent = tmp_path / "missing.yaml"

        with pytest.raises(ConfigError):
            find_config(str(nonexistent))

    def test_find_config_default(self, tmp_path):
        """Falls back to config.yaml in current directory."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("asr_provider: groq\nllm_provider: deepseek\n")

        result = find_config(None, search_dir=tmp_path)

        assert result == config_file

    def test_find_config_not_found(self, tmp_path):
        """Raises ConfigError when no config found."""
        with pytest.raises(ConfigError):
            find_config(None, search_dir=tmp_path)


class TestLoadAndValidateConfig:
    """Test config loading and validation."""

    def test_load_valid_config(self, tmp_path):
        """Loads and validates config successfully."""
        input_video = tmp_path / "test.mp4"
        input_video.touch()

        config_content = (
            f"asr_provider: groq\n"
            f"llm_provider: deepseek\n"
            f"input_video: {input_video}\n"
            f"output_dir: {tmp_path / 'output'}\n"
            f"max_budget_usd: 5.0\n"
        )
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = load_and_validate_config(config_file)

        assert config.asr_provider == "groq"
        assert config.max_budget_usd == 5.0

    def test_load_missing_input_video(self, tmp_path):
        """Raises ConfigError when input video not found."""
        config_content = (
            "asr_provider: groq\n"
            "llm_provider: deepseek\n"
            "input_video: /nonexistent/video.mp4\n"
        )
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        with pytest.raises(ConfigError):
            load_and_validate_config(config_file)


class TestSetupProgressDisplay:
    """Test TUI progress display setup."""

    def test_setup_returns_callback(self, tmp_path):
        """setup_progress_display returns a callable callback."""
        callback = setup_progress_display()

        assert callable(callback)

    def test_callback_accepts_progress_event(self, tmp_path):
        """Callback accepts and processes ProgressEvent."""
        from src.utils.progress import ProgressEvent, ProgressEventType

        callback = setup_progress_display()

        # Should not raise
        event = ProgressEvent(
            type=ProgressEventType.STAGE_START,
            stage="extract",
            stage_index=0,
            total_stages=5,
        )
        callback(event)


class TestSetupOrchestrator:
    """Test orchestrator setup."""

    def test_setup_creates_orchestrator(self, tmp_path):
        """setup_orchestrator returns PipelineOrchestrator instance."""
        from src.config import Config

        input_video = tmp_path / "test.mp4"
        input_video.touch()
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        config = Config(
            asr_provider="groq",
            llm_provider="deepseek",
            input_video=input_video,
            output_dir=output_dir,
            max_budget_usd=5.0,
        )
        callback = MagicMock()

        orchestrator = setup_orchestrator(config, callback)

        assert orchestrator is not None
        assert orchestrator.config == config
        assert orchestrator.progress_callback == callback


class TestCLI:
    """Test CLI entry point."""

    def test_cli_no_args_shows_help(self):
        """Running without args prints help and exits with error."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["echo-bering"]):
                cli()

        # argparse exits with code 2 for missing required args
        assert exc_info.value.code != 0

    def test_cli_with_config_path(self, tmp_path):
        """CLI accepts --config argument."""
        input_video = tmp_path / "test.mp4"
        input_video.touch()

        config_content = (
            f"asr_provider: groq\n"
            f"llm_provider: deepseek\n"
            f"input_video: {input_video}\n"
            f"output_dir: {tmp_path / 'output'}\n"
        )
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        with patch("sys.argv", ["echo-bering", "--config", str(config_file)]):
            with patch("src.main.run_pipeline", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = True
                with pytest.raises(SystemExit) as exc_info:
                    cli()

                # Should have called run_pipeline
                assert mock_run.called

    def test_cli_with_custom_output(self, tmp_path):
        """CLI accepts --output argument."""
        input_video = tmp_path / "test.mp4"
        input_video.touch()

        config_content = (
            f"asr_provider: groq\n"
            f"llm_provider: deepseek\n"
            f"input_video: {input_video}\n"
            f"max_budget_usd: 5.0\n"
        )
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        output_dir = tmp_path / "custom-output"

        with patch("sys.argv", [
            "echo-bering",
            "--config", str(config_file),
            "--output", str(output_dir),
        ]):
            with patch("src.main.run_pipeline", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = True
                with pytest.raises(SystemExit):
                    cli()

                # Verify the config passed to run_pipeline has correct output
                call_args = mock_run.call_args
                config_arg = call_args[0][0]
                assert config_arg.output_dir == output_dir

    def test_cli_with_budget_override(self, tmp_path):
        """CLI accepts --budget argument."""
        input_video = tmp_path / "test.mp4"
        input_video.touch()

        config_content = (
            f"asr_provider: groq\n"
            f"llm_provider: deepseek\n"
            f"input_video: {input_video}\n"
            f"max_budget_usd: 5.0\n"
        )
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        with patch("sys.argv", [
            "echo-bering",
            "--config", str(config_file),
            "--budget", "10.0",
        ]):
            with patch("src.main.run_pipeline", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = True
                with pytest.raises(SystemExit):
                    cli()

                call_args = mock_run.call_args
                config_arg = call_args[0][0]
                assert config_arg.max_budget_usd == 10.0


class TestRunPipeline:
    """Test run_pipeline function."""

    @pytest.mark.asyncio
    async def test_run_pipeline_success(self, tmp_path):
        """run_pipeline returns True on success."""
        from src.config import Config
        from src.orchestrators.pipeline import StageResult

        input_video = tmp_path / "test.mp4"
        input_video.touch()
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        config = Config(
            asr_provider="groq",
            llm_provider="deepseek",
            input_video=input_video,
            output_dir=output_dir,
            max_budget_usd=5.0,
        )

        with patch("src.main.setup_orchestrator") as mock_setup:
            mock_orchestrator = MagicMock()
            mock_orchestrator.execute = AsyncMock(
                return_value=StageResult.success("materialize")
            )
            mock_setup.return_value = mock_orchestrator

            from src.main import run_pipeline
            result = await run_pipeline(config, MagicMock())

            assert result is True

    @pytest.mark.asyncio
    async def test_run_pipeline_failure(self, tmp_path):
        """run_pipeline returns False on stage failure."""
        from src.config import Config
        from src.orchestrators.pipeline import StageResult
        from src.utils.errors import ProviderError

        input_video = tmp_path / "test.mp4"
        input_video.touch()
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        config = Config(
            asr_provider="groq",
            llm_provider="deepseek",
            input_video=input_video,
            output_dir=output_dir,
            max_budget_usd=5.0,
        )

        with patch("src.main.setup_orchestrator") as mock_setup:
            mock_orchestrator = MagicMock()
            mock_orchestrator.execute = AsyncMock(
                return_value=StageResult.failure(
                    "transcribe",
                    ProviderError("ASR failed"),
                )
            )
            mock_setup.return_value = mock_orchestrator

            from src.main import run_pipeline
            result = await run_pipeline(config, MagicMock())

            assert result is False

    @pytest.mark.asyncio
    async def test_run_pipeline_budget_error(self, tmp_path):
        """run_pipeline handles BudgetError gracefully."""
        from src.config import Config
        from src.utils.errors import BudgetError

        input_video = tmp_path / "test.mp4"
        input_video.touch()
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        config = Config(
            asr_provider="groq",
            llm_provider="deepseek",
            input_video=input_video,
            output_dir=output_dir,
            max_budget_usd=5.0,
        )

        with patch("src.main.setup_orchestrator") as mock_setup:
            mock_orchestrator = MagicMock()
            mock_orchestrator.execute = AsyncMock(
                side_effect=BudgetError(current_cost=10.0, max_budget=5.0)
            )
            mock_setup.return_value = mock_orchestrator

            from src.main import run_pipeline
            result = await run_pipeline(config, MagicMock())

            assert result is False

    @pytest.mark.asyncio
    async def test_run_pipeline_unexpected_error(self, tmp_path):
        """run_pipeline handles unexpected errors."""
        from src.config import Config

        input_video = tmp_path / "test.mp4"
        input_video.touch()
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        config = Config(
            asr_provider="groq",
            llm_provider="deepseek",
            input_video=input_video,
            output_dir=output_dir,
            max_budget_usd=5.0,
        )

        with patch("src.main.setup_orchestrator") as mock_setup:
            mock_orchestrator = MagicMock()
            mock_orchestrator.execute = AsyncMock(
                side_effect=RuntimeError("Unexpected crash")
            )
            mock_setup.return_value = mock_orchestrator

            from src.main import run_pipeline
            result = await run_pipeline(config, MagicMock())

            assert result is False


class TestCLIErrorHandling:
    """Test CLI error handling paths."""

    def test_cli_config_error_exits_2(self, tmp_path):
        """CLI exits with code 2 on config error."""
        nonexistent = tmp_path / "missing.yaml"

        with patch("sys.argv", ["echo-bering", "--config", str(nonexistent)]):
            with pytest.raises(SystemExit) as exc_info:
                cli()

            assert exc_info.value.code == 2

    def test_cli_unexpected_error_exits_1(self, tmp_path):
        """CLI exits with code 1 on unexpected error."""
        with patch("sys.argv", ["echo-bering"]):
            # Force an unexpected error during config loading
            with patch("src.main.find_config", side_effect=RuntimeError("crash")):
                with pytest.raises(SystemExit) as exc_info:
                    cli()

                assert exc_info.value.code == 1


class TestProgressDisplayCallbacks:
    """Test progress display callback handling for all event types."""

    def test_callback_stage_progress(self):
        """Callback handles STAGE_PROGRESS event."""
        from src.utils.progress import ProgressEvent, ProgressEventType

        callback = setup_progress_display()
        event = ProgressEvent(
            type=ProgressEventType.STAGE_PROGRESS,
            stage="extract",
            progress=0.5,
            eta_seconds=120.0,
        )
        # Should not raise
        callback(event)

    def test_callback_stage_complete(self):
        """Callback handles STAGE_COMPLETE event."""
        from src.utils.progress import ProgressEvent, ProgressEventType

        callback = setup_progress_display()
        event = ProgressEvent(
            type=ProgressEventType.STAGE_COMPLETE,
            stage="extract",
            stage_index=0,
            total_stages=5,
            duration_seconds=30.0,
        )
        callback(event)

    def test_callback_stage_error(self):
        """Callback handles STAGE_ERROR event."""
        from src.utils.progress import ProgressEvent, ProgressEventType

        callback = setup_progress_display()
        event = ProgressEvent(
            type=ProgressEventType.STAGE_ERROR,
            stage="transcribe",
            message="ASR failed",
            error_type="ProviderError",
        )
        callback(event)

    def test_callback_cost_update(self):
        """Callback handles COST_UPDATE event."""
        from src.utils.progress import ProgressEvent, ProgressEventType

        callback = setup_progress_display()
        event = ProgressEvent(
            type=ProgressEventType.COST_UPDATE,
            stage="transcribe",
            cost_usd=1.50,
            budget_usd=5.0,
        )
        callback(event)

    def test_callback_warning(self):
        """Callback handles WARNING event."""
        from src.utils.progress import ProgressEvent, ProgressEventType

        callback = setup_progress_display()
        event = ProgressEvent(
            type=ProgressEventType.WARNING,
            message="Low transcription confidence",
        )
        callback(event)

    def test_callback_chapter_complete(self):
        """Callback handles CHAPTER_COMPLETE event."""
        from src.utils.progress import ProgressEvent, ProgressEventType

        callback = setup_progress_display()
        event = ProgressEvent(
            type=ProgressEventType.CHAPTER_COMPLETE,
            chapter_slug="introduction",
            chapter_number=1,
            total_chapters=5,
        )
        callback(event)
