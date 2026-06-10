"""Unit tests for PipelineOrchestrator — stage-based execution with checkpointing."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from src.config import Config
from src.models.chapter import Chapter
from src.orchestrators.pipeline import (
    STAGE_EXTRACT,
    STAGE_ENRICH,
    STAGE_MATERIALIZE,
    STAGE_SEGMENT,
    STAGE_TRANSCRIBE,
    STAGE_ORDER,
    PipelineOrchestrator,
    StageResult,
)
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.llm.base import LLMResponse
from src.utils.cost_estimator import CostEstimator
from src.utils.errors import BudgetError, ProviderError
from src.utils.progress import ProgressEvent, ProgressEventType, PipelineState


def _make_mock_config(tmp_path):
    """Create a mock Config for testing."""
    input_video = tmp_path / "test.mp4"
    input_video.touch()
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        asr_provider="groq",
        llm_provider="deepseek",
        input_video=input_video,
        output_dir=output_dir,
        max_budget_usd=10.0,
    )


def _make_transcript_result():
    """Create a mock TranscriptResult."""
    return TranscriptResult(
        text="Sample transcription of the video content.",
        confidence=0.92,
        words=[
            WordTimestamp(word="Sample", start=0.0, end=0.5, confidence=0.95),
            WordTimestamp(word="transcription", start=0.6, end=1.0, confidence=0.90),
        ],
        duration_s=150.0,
        provider="mock",
        model="mock-model",
    )


def _make_chapters():
    """Create mock chapters from segmentation."""
    return [
        Chapter(
            number=1,
            title="Introduction",
            start_time="00:00:00.000",
            end_time="00:02:30.000",
            start_seconds=0.0,
            end_seconds=150.0,
            confidence=0.85,
            transcript="Sample transcription of the video content.",
            needs_review=False,
        )
    ]


class TestStageResult:
    """Test StageResult dataclass."""

    def test_success_result(self):
        """Successful stage result."""
        result = StageResult.success("extract", data={"path": "/audio.wav"})

        assert result.stage == "extract"
        assert result.success is True
        assert result.data == {"path": "/audio.wav"}
        assert result.error is None

    def test_failure_result(self):
        """Failed stage result."""
        error = ProviderError("API error")
        result = StageResult.failure("transcribe", error)

        assert result.stage == "transcribe"
        assert result.success is False
        assert result.error == error
        assert result.data is None


class TestStageOrder:
    """Test stage ordering constants."""

    def test_stage_order(self):
        """Stages are defined in correct order."""
        assert STAGE_ORDER == [
            STAGE_EXTRACT,
            STAGE_TRANSCRIBE,
            STAGE_SEGMENT,
            STAGE_ENRICH,
            STAGE_MATERIALIZE,
        ]

    def test_stage_constants(self):
        """Stage name constants are correct."""
        assert STAGE_EXTRACT == "extract"
        assert STAGE_TRANSCRIBE == "transcribe"
        assert STAGE_SEGMENT == "segment"
        assert STAGE_ENRICH == "enrich"
        assert STAGE_MATERIALIZE == "materialize"


class TestPipelineOrchestratorInit:
    """Test PipelineOrchestrator initialization."""

    def test_initialization_with_components(self, tmp_path):
        """Orchestrator initializes with all components."""
        config = _make_mock_config(tmp_path)

        orchestrator = PipelineOrchestrator(config=config)

        assert orchestrator.config == config
        assert orchestrator.cost_estimator is not None
        assert isinstance(orchestrator.cost_estimator, CostEstimator)
        assert orchestrator.pipeline_state is not None

    def test_initialization_with_callback(self, tmp_path):
        """Orchestrator stores progress callback."""
        config = _make_mock_config(tmp_path)
        callback = MagicMock()

        orchestrator = PipelineOrchestrator(
            config=config,
            progress_callback=callback,
        )

        assert orchestrator.progress_callback == callback


class TestPipelineOrchestratorExecute:
    """Test full pipeline execution."""

    @pytest.mark.asyncio
    async def test_execute_all_stages(self, tmp_path):
        """Pipeline executes all stages in order."""
        config = _make_mock_config(tmp_path)
        transcript = _make_transcript_result()
        chapters = _make_chapters()

        orchestrator = PipelineOrchestrator(config=config)
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": str(tmp_path / "audio.wav")})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.success(STAGE_TRANSCRIBE, data={"transcript": transcript})
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={"chapters": chapters})
        )
        orchestrator._execute_enrich = AsyncMock(
            return_value=StageResult.success(STAGE_ENRICH, data={"chapters": chapters})
        )
        orchestrator._execute_materialize = AsyncMock(
            return_value=StageResult.success(STAGE_MATERIALIZE, data={"chapters_dir": str(tmp_path / "chapters")})
        )

        result = await orchestrator.execute()

        assert result.success is True
        assert orchestrator._execute_extract.call_count == 1
        assert orchestrator._execute_transcribe.call_count == 1
        assert orchestrator._execute_segment.call_count == 1
        assert orchestrator._execute_enrich.call_count == 1
        assert orchestrator._execute_materialize.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_halts_on_failure(self, tmp_path):
        """Pipeline halts when a stage fails."""
        config = _make_mock_config(tmp_path)

        orchestrator = PipelineOrchestrator(config=config)
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.failure(
                STAGE_TRANSCRIBE,
                ProviderError("ASR API error"),
            )
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={})
        )

        result = await orchestrator.execute()

        assert result.success is False
        assert result.error is not None
        # Segment should NOT have been called
        assert orchestrator._execute_segment.call_count == 0

    @pytest.mark.asyncio
    async def test_execute_emits_progress_events(self, tmp_path):
        """Pipeline emits progress events during execution."""
        config = _make_mock_config(tmp_path)
        events = []

        def capture_event(event):
            events.append(event)

        orchestrator = PipelineOrchestrator(
            config=config,
            progress_callback=capture_event,
        )
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.success(STAGE_TRANSCRIBE, data={"transcript": _make_transcript_result()})
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_enrich = AsyncMock(
            return_value=StageResult.success(STAGE_ENRICH, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_materialize = AsyncMock(
            return_value=StageResult.success(STAGE_MATERIALIZE, data={"chapters_dir": str(tmp_path / "chapters")})
        )

        await orchestrator.execute()

        # Should have at least stage_start events for each stage
        stage_starts = [e for e in events if e.type == ProgressEventType.STAGE_START]
        assert len(stage_starts) == 5


class TestPipelineOrchestratorBudget:
    """Test budget enforcement."""

    @pytest.mark.asyncio
    async def test_budget_check_before_stage(self, tmp_path):
        """BudgetError raised when budget exceeded."""
        config = _make_mock_config(tmp_path)
        config.max_budget_usd = 1.0

        orchestrator = PipelineOrchestrator(config=config)
        orchestrator.cost_estimator.total_cost = 2.0  # Already over budget

        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )

        with pytest.raises(BudgetError):
            await orchestrator.execute()


class TestPipelineOrchestratorCheckpoint:
    """Test checkpoint-based resumption."""

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self, tmp_path):
        """Pipeline skips stages with checkpoints and resumes."""
        config = _make_mock_config(tmp_path)

        # Create checkpoint for extract stage
        checkpoint_dir = config.output_dir / ".checkpoint"
        (checkpoint_dir / STAGE_EXTRACT).mkdir(parents=True, exist_ok=True)
        (checkpoint_dir / STAGE_EXTRACT / "data.json").write_text(
            json.dumps({"audio_path": str(tmp_path / "audio.wav")})
        )

        orchestrator = PipelineOrchestrator(config=config)

        # Mock methods — extract should NOT be called
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.success(STAGE_TRANSCRIBE, data={"transcript": _make_transcript_result()})
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_enrich = AsyncMock(
            return_value=StageResult.success(STAGE_ENRICH, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_materialize = AsyncMock(
            return_value=StageResult.success(STAGE_MATERIALIZE, data={"chapters_dir": str(tmp_path / "chapters")})
        )

        result = await orchestrator.execute()

        assert result.success is True
        # Extract should be skipped due to checkpoint
        assert orchestrator._execute_extract.call_count == 0
        assert orchestrator._execute_transcribe.call_count == 1

    @pytest.mark.asyncio
    async def test_no_checkpoint_runs_all_stages(self, tmp_path):
        """Pipeline runs all stages when no checkpoints exist."""
        config = _make_mock_config(tmp_path)
        # No checkpoints — ensure directory is clean
        checkpoint_dir = config.output_dir / ".checkpoint"
        if checkpoint_dir.exists():
            import shutil
            shutil.rmtree(checkpoint_dir)

        orchestrator = PipelineOrchestrator(config=config)
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.success(STAGE_TRANSCRIBE, data={"transcript": _make_transcript_result()})
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_enrich = AsyncMock(
            return_value=StageResult.success(STAGE_ENRICH, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_materialize = AsyncMock(
            return_value=StageResult.success(STAGE_MATERIALIZE, data={"chapters_dir": str(tmp_path / "chapters")})
        )

        result = await orchestrator.execute()

        assert result.success is True
        # All stages should be called
        assert orchestrator._execute_extract.call_count == 1
        assert orchestrator._execute_transcribe.call_count == 1

    @pytest.mark.asyncio
    async def test_checkpoint_cleaned_on_success(self, tmp_path):
        """Checkpoints are cleaned up after successful pipeline run."""
        config = _make_mock_config(tmp_path)

        orchestrator = PipelineOrchestrator(config=config)
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": str(tmp_path / "audio.wav")})
        )
        # Make subsequent stages succeed quickly
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.success(STAGE_TRANSCRIBE, data={"transcript": _make_transcript_result()})
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_enrich = AsyncMock(
            return_value=StageResult.success(STAGE_ENRICH, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_materialize = AsyncMock(
            return_value=StageResult.success(STAGE_MATERIALIZE, data={"chapters_dir": str(tmp_path / "chapters")})
        )

        await orchestrator.execute()

        # Checkpoint directory should be cleaned up on success
        checkpoint_dir = config.output_dir / ".checkpoint"
        assert not checkpoint_dir.exists()


class TestPipelineOrchestratorState:
    """Test PipelineOrchestrator state management."""

    @pytest.mark.asyncio
    async def test_final_state_is_complete(self, tmp_path):
        """Pipeline state shows complete after successful run."""
        config = _make_mock_config(tmp_path)

        orchestrator = PipelineOrchestrator(config=config)
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.success(STAGE_TRANSCRIBE, data={"transcript": _make_transcript_result()})
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_enrich = AsyncMock(
            return_value=StageResult.success(STAGE_ENRICH, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_materialize = AsyncMock(
            return_value=StageResult.success(STAGE_MATERIALIZE, data={"chapters_dir": str(tmp_path / "chapters")})
        )

        await orchestrator.execute()

        assert orchestrator.pipeline_state.is_complete is True
        assert orchestrator.pipeline_state.is_running is False

    @pytest.mark.asyncio
    async def test_final_state_is_failed(self, tmp_path):
        """Pipeline state shows failed after error."""
        config = _make_mock_config(tmp_path)

        orchestrator = PipelineOrchestrator(config=config)
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.failure(
                STAGE_TRANSCRIBE,
                ProviderError("ASR failed"),
            )
        )

        await orchestrator.execute()

        assert orchestrator.pipeline_state.is_failed is True
        assert orchestrator.pipeline_state.is_running is False


class TestPipelineOrchestratorExecuteExtract:
    """Test _execute_extract method."""

    @pytest.mark.asyncio
    async def test_execute_extract_success(self, tmp_path):
        """Extract stage returns audio path on success."""
        from unittest.mock import patch

        config = _make_mock_config(tmp_path)
        orchestrator = PipelineOrchestrator(config=config)

        with patch("src.orchestrators.pipeline.AudioExtractor") as mock_extractor:
            mock_instance = MagicMock()
            mock_instance.extract.return_value = tmp_path / "audio.wav"
            mock_extractor.return_value = mock_instance

            result = await orchestrator._execute_extract()

        assert result.success is True
        assert result.data is not None
        assert "audio_path" in result.data

    @pytest.mark.asyncio
    async def test_execute_extract_failure(self, tmp_path):
        """Extract stage failure returns StageResult with error."""
        from unittest.mock import patch

        config = _make_mock_config(tmp_path)
        config.input_video = tmp_path / "nonexistent.mp4"
        config.input_video.touch()  # File exists but won't work with ffmpeg
        orchestrator = PipelineOrchestrator(config=config)

        with patch("src.orchestrators.pipeline.AudioExtractor") as mock_extractor:
            mock_extractor.side_effect = RuntimeError("ffmpeg extraction failed")
            result = await orchestrator._execute_extract()

        assert result.success is False
        assert result.error is not None


class TestPipelineOrchestratorExecuteTranscribe:
    """Test _execute_transcribe method."""

    @pytest.mark.asyncio
    async def test_execute_transcribe_low_confidence_warning(self, tmp_path):
        """Emits warning when transcription confidence below threshold."""
        config = _make_mock_config(tmp_path)
        config.transcription_confidence_threshold = 0.95  # High threshold

        events = []
        orchestrator = PipelineOrchestrator(
            config=config,
            progress_callback=lambda e: events.append(e),
        )

        # Create audio checkpoint for transcribe to find
        audio_checkpoint = config.output_dir / ".checkpoint" / "extract"
        audio_checkpoint.mkdir(parents=True, exist_ok=True)
        (audio_checkpoint / "data.json").write_text(
            json.dumps({"audio_path": str(tmp_path / "audio.wav")})
        )
        # Create the fake audio file
        (tmp_path / "audio.wav").write_bytes(b"fake audio")

        with patch("src.orchestrators.pipeline.Transcriber") as mock_transcriber:
            mock_instance = MagicMock()
            mock_instance.transcribe = AsyncMock(return_value=_make_transcript_result())
            mock_transcriber.return_value = mock_instance

            with patch("src.orchestrators.pipeline.create_asr_provider"):
                result = await orchestrator._execute_transcribe()

        assert result.success is True
        # Should have a warning event for low confidence
        warnings = [e for e in events if e.type == ProgressEventType.WARNING]
        assert len(warnings) >= 1


class TestPipelineOrchestratorExecuteSegment:
    """Test _execute_segment method."""

    @pytest.mark.asyncio
    async def test_execute_segment_no_transcript_checkpoint(self, tmp_path):
        """Returns failure when no transcript checkpoint exists."""
        config = _make_mock_config(tmp_path)
        orchestrator = PipelineOrchestrator(config=config)

        result = await orchestrator._execute_segment()

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_segment_low_confidence_warning(self, tmp_path):
        """Emits warning when segmentation confidence below threshold."""
        config = _make_mock_config(tmp_path)
        config.segmentation_confidence_threshold = 0.95  # High threshold

        events = []
        orchestrator = PipelineOrchestrator(
            config=config,
            progress_callback=lambda e: events.append(e),
        )

        # Create transcript checkpoint
        transcribe_checkpoint = config.output_dir / ".checkpoint" / "transcribe"
        transcribe_checkpoint.mkdir(parents=True, exist_ok=True)
        (transcribe_checkpoint / "data.json").write_text(
            json.dumps({"text": "Sample transcript content"})
        )

        chapters = _make_chapters()
        chapters[0].confidence = 0.5  # Low confidence

        with patch("src.orchestrators.pipeline.create_llm_provider"):
            with patch("src.orchestrators.pipeline.ChapterSegmenter") as mock_segmenter:
                mock_instance = MagicMock()
                mock_instance.segment = AsyncMock(return_value=chapters)
                mock_segmenter.return_value = mock_instance

                result = await orchestrator._execute_segment()

        assert result.success is True
        warnings = [e for e in events if e.type == ProgressEventType.WARNING]
        assert len(warnings) >= 1


class TestPipelineOrchestratorExecuteEnrich:
    """Test _execute_enrich method."""

    @pytest.mark.asyncio
    async def test_execute_enrich_no_chapters_checkpoint(self, tmp_path):
        """Returns failure when no chapters checkpoint exists."""
        config = _make_mock_config(tmp_path)
        orchestrator = PipelineOrchestrator(config=config)

        result = await orchestrator._execute_enrich()

        assert result.success is False
        assert result.error is not None


class TestPipelineOrchestratorFindResume:
    """Test _find_resume_stage method."""

    def test_find_resume_all_checkpoints_exist(self, tmp_path):
        """Returns 0 when all stages have checkpoints."""
        config = _make_mock_config(tmp_path)

        # Create checkpoints for all stages
        for stage in STAGE_ORDER:
            (config.output_dir / ".checkpoint" / stage).mkdir(parents=True, exist_ok=True)
            (config.output_dir / ".checkpoint" / stage / "data.json").write_text("{}")

        orchestrator = PipelineOrchestrator(config=config)
        result = orchestrator._find_resume_stage()

        # All stages have checkpoints — restart from beginning
        assert result == 0

    def test_find_resume_partial_checkpoints(self, tmp_path):
        """Returns index of first missing checkpoint."""
        config = _make_mock_config(tmp_path)

        # Only create extract checkpoint
        (config.output_dir / ".checkpoint" / "extract").mkdir(parents=True, exist_ok=True)
        (config.output_dir / ".checkpoint" / "extract" / "data.json").write_text("{}")

        orchestrator = PipelineOrchestrator(config=config)
        result = orchestrator._find_resume_stage()

        # Should resume from transcribe (index 1)
        assert result == 1


class TestPipelineOrchestratorUnknownStage:
    """Test unknown stage handling."""

    @pytest.mark.asyncio
    async def test_execute_stage_unknown_name(self, tmp_path):
        """Returns failure for unknown stage name."""
        config = _make_mock_config(tmp_path)
        orchestrator = PipelineOrchestrator(config=config)

        result = await orchestrator._execute_stage("unknown_stage", 0)

        assert result.success is False
        assert isinstance(result.error, ValueError)
        assert "Unknown stage" in str(result.error)
