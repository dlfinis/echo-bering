"""Integration tests for end-to-end pipeline flow.

Tests the full pipeline from configuration to output with mocked providers.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config, load_config
from src.models.chapter import Chapter, EnrichedChapter, Highlight
from src.orchestrators.pipeline import (
    PipelineOrchestrator,
    StageResult,
    STAGE_EXTRACT,
    STAGE_TRANSCRIBE,
    STAGE_SEGMENT,
    STAGE_ENRICH,
    STAGE_MATERIALIZE,
)
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.providers.llm.base import LLMResponse
from src.utils.progress import ProgressEvent, ProgressEventType


def _make_config(tmp_path):
    """Create a test config with valid paths."""
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


def _make_transcript():
    """Create a mock transcript result."""
    return TranscriptResult(
        text="Welcome to this video. Today we will learn about Python programming. "
             "First, let us discuss variables. Variables store data values. "
             "Next, we will cover functions. Functions are reusable code blocks.",
        confidence=0.92,
        words=[
            WordTimestamp(word="Welcome", start=0.0, end=0.5, confidence=0.95),
            WordTimestamp(word="to", start=0.6, end=0.8, confidence=0.93),
            WordTimestamp(word="this", start=0.9, end=1.1, confidence=0.94),
            WordTimestamp(word="video.", start=1.2, end=1.5, confidence=0.92),
            WordTimestamp(word="Today", start=10.0, end=10.5, confidence=0.91),
            WordTimestamp(word="we", start=10.6, end=10.8, confidence=0.90),
            WordTimestamp(word="will", start=10.9, end=11.1, confidence=0.89),
            WordTimestamp(word="learn", start=11.2, end=11.5, confidence=0.91),
        ],
        duration_s=300.0,
        provider="mock",
        model="mock-model",
    )


def _make_chapters():
    """Create mock chapters."""
    return [
        Chapter(
            number=1,
            title="Introduction",
            start_time="00:00:00.000",
            end_time="00:01:30.000",
            start_seconds=0.0,
            end_seconds=90.0,
            confidence=0.88,
            transcript="Welcome to this video. Today we will learn about Python programming.",
            needs_review=False,
        ),
        Chapter(
            number=2,
            title="Variables and Functions",
            start_time="00:01:30.000",
            end_time="00:05:00.000",
            start_seconds=90.0,
            end_seconds=300.0,
            confidence=0.85,
            transcript="First, let us discuss variables. Variables store data values. Next, we will cover functions.",
            needs_review=False,
        ),
    ]


def _make_enriched_chapters():
    """Create mock enriched chapters."""
    chapters = _make_chapters()
    return [
        EnrichedChapter(
            chapter=chapters[0],
            description="Introduction to Python programming",
            context="First chapter of the video",
            summary_bullets=["Welcome message", "Course overview"],
            terms_used=[{"term": "Python", "type": "lenguaje", "frequency": 2, "definition": "Programming language"}],
            key_concepts=["Python", "Programming"],
            entities_detected={"tecnologías": ["Python"]},
            highlights=[
                Highlight(
                    timestamp="00:00:30",
                    type="insight",
                    label="Idea clave",
                    quote="Python makes programming accessible",
                    importance="alta",
                )
            ],
            pedagogy={"difficulty_level": "principiante"},
            confidence={"segmentation_score": 0.88, "needs_review": False},
        ),
        EnrichedChapter(
            chapter=chapters[1],
            description="Variables and functions in Python",
            context="Follows introduction",
            summary_bullets=["Variables store data", "Functions are reusable"],
            terms_used=[{"term": "Function", "type": "concepto", "frequency": 3, "definition": "Code block"}],
            key_concepts=["Variables", "Functions"],
            entities_detected={},
            highlights=[],
            pedagogy={"difficulty_level": "principiante"},
            confidence={"segmentation_score": 0.85, "needs_review": False},
        ),
    ]


class TestEndToEndPipeline:
    """Test full end-to-end pipeline execution with mocked components."""

    @patch("shutil.which")
    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_full_pipeline_execution(self, mock_run, mock_which, tmp_path):
        """Pipeline runs all stages and produces expected output files."""
        # Setup ffmpeg mock
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        config = _make_config(tmp_path)
        events = []

        def capture_event(event):
            events.append(event)

        orchestrator = PipelineOrchestrator(config=config, progress_callback=capture_event)
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": str(tmp_path / "audio.wav")})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.success(STAGE_TRANSCRIBE, data={"transcript": _make_transcript()})
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_enrich = AsyncMock(
            return_value=StageResult.success(STAGE_ENRICH, data={"chapters": _make_enriched_chapters()})
        )
        orchestrator._execute_materialize = AsyncMock(
            return_value=StageResult.success(STAGE_MATERIALIZE, data={"chapters_dir": str(config.output_dir / "chapters")})
        )

        result = await orchestrator.execute()

        assert result.success is True
        assert len(events) > 0

        # Verify all stages were started
        stage_starts = {e.stage for e in events if e.type == ProgressEventType.STAGE_START}
        assert STAGE_EXTRACT in stage_starts
        assert STAGE_TRANSCRIBE in stage_starts
        assert STAGE_SEGMENT in stage_starts
        assert STAGE_ENRICH in stage_starts
        assert STAGE_MATERIALIZE in stage_starts

    @patch("shutil.which")
    @patch("subprocess.run")
    @pytest.mark.asyncio
    async def test_pipeline_with_checkpoint_resumption(self, mock_run, mock_which, tmp_path):
        """Pipeline resumes from checkpoint and skips completed stages."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        config = _make_config(tmp_path)

        # Create checkpoints for extract and transcribe
        checkpoint_dir = config.output_dir / ".checkpoint"
        (checkpoint_dir / STAGE_EXTRACT).mkdir(parents=True, exist_ok=True)
        (checkpoint_dir / STAGE_EXTRACT / "data.json").write_text(
            json.dumps({"audio_path": str(tmp_path / "audio.wav")})
        )
        (checkpoint_dir / STAGE_TRANSCRIBE).mkdir(parents=True, exist_ok=True)
        (checkpoint_dir / STAGE_TRANSCRIBE / "data.json").write_text(
            json.dumps({"text": "Previous transcript", "confidence": 0.90, "words": [], "duration_s": 100.0})
        )

        orchestrator = PipelineOrchestrator(config=config)
        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )
        orchestrator._execute_transcribe = AsyncMock(
            return_value=StageResult.success(STAGE_TRANSCRIBE, data={"transcript": _make_transcript()})
        )
        orchestrator._execute_segment = AsyncMock(
            return_value=StageResult.success(STAGE_SEGMENT, data={"chapters": _make_chapters()})
        )
        orchestrator._execute_enrich = AsyncMock(
            return_value=StageResult.success(STAGE_ENRICH, data={"chapters": _make_enriched_chapters()})
        )
        orchestrator._execute_materialize = AsyncMock(
            return_value=StageResult.success(STAGE_MATERIALIZE, data={"chapters_dir": str(config.output_dir / "chapters")})
        )

        result = await orchestrator.execute()

        assert result.success is True
        # Extract and transcribe should be skipped
        assert orchestrator._execute_extract.call_count == 0
        assert orchestrator._execute_transcribe.call_count == 0
        # Segment, enrich, materialize should run
        assert orchestrator._execute_segment.call_count == 1
        assert orchestrator._execute_enrich.call_count == 1
        assert orchestrator._execute_materialize.call_count == 1


class TestBudgetEnforcementIntegration:
    """Test budget enforcement in pipeline context."""

    @pytest.mark.asyncio
    async def test_pipeline_stops_when_budget_exceeded(self, tmp_path):
        """Pipeline raises BudgetError when cost exceeds limit."""
        config = _make_config(tmp_path)
        config.max_budget_usd = 0.01  # Very low budget

        orchestrator = PipelineOrchestrator(config=config)
        # Artificially set high cost
        orchestrator.cost_estimator.total_cost = 1.0

        orchestrator._execute_extract = AsyncMock(
            return_value=StageResult.success(STAGE_EXTRACT, data={"audio_path": "audio.wav"})
        )

        from src.utils.errors import BudgetError
        with pytest.raises(BudgetError):
            await orchestrator.execute()


class TestOutputStructureIntegration:
    """Test output file structure and content."""

    @pytest.mark.asyncio
    async def test_materialize_produces_correct_structure(self, tmp_path):
        """Materialization creates expected folder structure."""
        from src.processors.materializer import ChapterMaterializer

        materializer = ChapterMaterializer(output_dir=tmp_path)
        chapters = _make_chapters()
        transcript = _make_transcript()

        for chapter in chapters:
            materializer.materialize(
                chapter=chapter,
                transcript=transcript,
                source_video=None,
            )

        # Check folder structure
        chapters_dir = tmp_path / "chapters"
        assert chapters_dir.exists()

        for chapter in chapters:
            slug = chapter.title.lower().replace(" ", "-")
            chapter_dir = chapters_dir / slug

            assert chapter_dir.exists(), f"Chapter dir missing: {chapter_dir}"
            assert (chapter_dir / "metadata.json").exists(), f"metadata.json missing for {slug}"
            assert (chapter_dir / f"{slug}.srt").exists(), f"SRT missing for {slug}"

    @pytest.mark.asyncio
    async def test_metadata_json_matches_schema(self, tmp_path):
        """metadata.json conforms to the expected schema."""
        from src.processors.materializer import ChapterMaterializer

        materializer = ChapterMaterializer(output_dir=tmp_path)
        chapters = _make_chapters()
        transcript = _make_transcript()

        materializer.materialize(
            chapter=chapters[0],
            transcript=transcript,
            source_video=None,
        )

        slug = chapters[0].title.lower().replace(" ", "-")
        metadata_path = tmp_path / "chapters" / slug / "metadata.json"

        with open(metadata_path, "r") as f:
            data = json.load(f)

        # Verify required fields per spec
        assert "title" in data
        assert "slug" in data
        assert "start_time" in data
        assert "end_time" in data
        assert "start_seconds" in data
        assert "end_seconds" in data
        assert "summary" in data
        assert "key_topics" in data
        assert "confidence" in data
        assert "transcription_confidence" in data

        # Verify values
        assert data["title"] == chapters[0].title
        assert data["start_seconds"] == chapters[0].start_seconds
        assert data["transcription_confidence"] == transcript.confidence

    @pytest.mark.asyncio
    async def test_srt_file_content(self, tmp_path):
        """SRT file has correct format."""
        from src.processors.materializer import ChapterMaterializer

        materializer = ChapterMaterializer(output_dir=tmp_path)
        chapters = _make_chapters()
        transcript = _make_transcript()

        materializer.materialize(
            chapter=chapters[0],
            transcript=transcript,
            source_video=None,
        )

        slug = chapters[0].title.lower().replace(" ", "-")
        srt_path = tmp_path / "chapters" / slug / f"{slug}.srt"

        content = srt_path.read_text()
        # SRT entries start with sequential number
        assert "1\n" in content
        # Timestamps in SRT format
        assert "-->" in content
        # Word text present
        assert "Welcome" in content
