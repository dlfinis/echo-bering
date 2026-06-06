"""Pipeline orchestrator — coordinates all processing stages.

PipelineOrchestrator executes the pipeline stages sequentially with
checkpoint-based resumption, cost tracking, and progress reporting.
"""

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.config import Config
from src.models.chapter import Chapter, EnrichedChapter
from src.processors.audio_extractor import AudioExtractor
from src.processors.enricher import MetadataEnricher
from src.processors.materializer import ChapterMaterializer
from src.processors.segmenter import ChapterSegmenter, PromptManager
from src.processors.transcriber import Transcriber
from src.providers.asr.base import TranscriptResult
from src.providers.factory import create_asr_provider, create_llm_provider
from src.utils.checkpoint import CheckpointManager
from src.utils.cost_estimator import CostEstimator
from src.utils.errors import BudgetError, ProviderError
from src.utils.logger import get_logger
from src.utils.progress import (
    PipelineState,
    ProgressEvent,
    ProgressEventType,
)

logger = get_logger(__name__)

# Stage name constants
STAGE_EXTRACT = "extract"
STAGE_TRANSCRIBE = "transcribe"
STAGE_SEGMENT = "segment"
STAGE_ENRICH = "enrich"
STAGE_MATERIALIZE = "materialize"

STAGE_ORDER = [
    STAGE_EXTRACT,
    STAGE_TRANSCRIBE,
    STAGE_SEGMENT,
    STAGE_ENRICH,
    STAGE_MATERIALIZE,
]


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""

    stage: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[Exception] = None

    @classmethod
    def success(cls, stage: str, data: Optional[Dict[str, Any]] = None) -> "StageResult":
        return cls(stage=stage, success=True, data=data)

    @classmethod
    def failure(cls, stage: str, error: Exception) -> "StageResult":
        return cls(stage=stage, success=False, error=error)


# Re-export for imports from the same module
__all__ = [
    "STAGE_EXTRACT",
    "STAGE_TRANSCRIBE",
    "STAGE_SEGMENT",
    "STAGE_ENRICH",
    "STAGE_MATERIALIZE",
    "STAGE_ORDER",
    "PipelineOrchestrator",
    "StageResult",
]


class PipelineOrchestrator:
    """Orchestrate the full pipeline execution.

    Coordinates all stages: extract → transcribe → segment → enrich → materialize.
    Supports checkpoint-based resumption and budget enforcement.
    """

    def __init__(
        self,
        config: Config,
        progress_callback: Optional[Callable[[ProgressEvent], None]] = None,
    ):
        """Initialize PipelineOrchestrator.

        Args:
            config: Validated pipeline configuration.
            progress_callback: Optional callback for progress events.
        """
        self.config = config
        self.progress_callback = progress_callback
        self.cost_estimator = CostEstimator()
        self.checkpoint_manager = CheckpointManager(config.output_dir)
        self.pipeline_state = PipelineState(total_stages=len(STAGE_ORDER))

        # Components (lazily initialized)
        self._audio_extractor: Optional[AudioExtractor] = None
        self._transcriber: Optional[Transcriber] = None
        self._segmenter: Optional[ChapterSegmenter] = None
        self._enricher: Optional[MetadataEnricher] = None
        self._materializer: Optional[ChapterMaterializer] = None

    def _emit(self, event: ProgressEvent) -> None:
        """Emit a progress event to the callback and update state.

        Args:
            event: The progress event to emit.
        """
        self.pipeline_state.apply(event)
        if self.progress_callback:
            self.progress_callback(event)

    async def execute(self) -> StageResult:
        """Execute the full pipeline.

        Returns:
            StageResult with overall success/failure status.

        Raises:
            BudgetError: If cumulative cost exceeds configured budget.
        """
        logger.info("Starting pipeline execution — %d stages", len(STAGE_ORDER))

        # Determine starting stage based on checkpoints
        start_index = self._find_resume_stage()

        # Execute stages from resume point
        for i, stage_name in enumerate(STAGE_ORDER):
            if i < start_index:
                logger.info("Skipping stage '%s' — checkpoint exists", stage_name)
                continue

            # Budget check before each stage
            self.cost_estimator.check_budget(self.config.max_budget_usd)

            try:
                result = await self._execute_stage(stage_name, i)
                if not result.success:
                    logger.error("Stage '%s' failed: %s", stage_name, result.error)
                    self._emit(ProgressEvent(
                        type=ProgressEventType.STAGE_ERROR,
                        stage=stage_name,
                        message=str(result.error),
                        error_type=type(result.error).__name__,
                    ))
                    return StageResult.failure(stage_name, result.error)

                # Save checkpoint after successful stage
                if result.data:
                    self.checkpoint_manager.save(stage_name, self._serialize_data(result.data))

                self._emit(ProgressEvent(
                    type=ProgressEventType.STAGE_COMPLETE,
                    stage=stage_name,
                    stage_index=i,
                    total_stages=len(STAGE_ORDER),
                    duration_seconds=0.0,
                ))

            except BudgetError:
                raise
            except Exception as e:
                logger.error("Stage '%s' crashed: %s", stage_name, e)
                self._emit(ProgressEvent(
                    type=ProgressEventType.STAGE_ERROR,
                    stage=stage_name,
                    message=str(e),
                    error_type=type(e).__name__,
                ))
                return StageResult.failure(stage_name, e)

        # Clean up checkpoints on success
        self.checkpoint_manager.clear()
        logger.info("Pipeline completed successfully")

        return StageResult.success(STAGE_MATERIALIZE, data={"output_dir": str(self.config.output_dir)})

    async def _execute_stage(self, stage_name: str, stage_index: int) -> StageResult:
        """Execute a single pipeline stage.

        Args:
            stage_name: Name of the stage to execute.
            stage_index: Zero-based index in the stage order.

        Returns:
            StageResult with stage outcome.
        """
        self._emit(ProgressEvent(
            type=ProgressEventType.STAGE_START,
            stage=stage_name,
            stage_index=stage_index,
            total_stages=len(STAGE_ORDER),
        ))

        if stage_name == STAGE_EXTRACT:
            return await self._execute_extract()
        elif stage_name == STAGE_TRANSCRIBE:
            return await self._execute_transcribe()
        elif stage_name == STAGE_SEGMENT:
            return await self._execute_segment()
        elif stage_name == STAGE_ENRICH:
            return await self._execute_enrich()
        elif stage_name == STAGE_MATERIALIZE:
            return await self._execute_materialize()
        else:
            return StageResult.failure(stage_name, ValueError(f"Unknown stage: {stage_name}"))

    async def _execute_extract(self) -> StageResult:
        """Execute the audio extraction stage."""
        try:
            extractor = AudioExtractor(self.config.output_dir)
            audio_path = extractor.extract(str(self.config.input_video))

            self._emit(ProgressEvent(
                type=ProgressEventType.STAGE_PROGRESS,
                stage=STAGE_EXTRACT,
                progress=1.0,
            ))

            return StageResult.success(STAGE_EXTRACT, data={"audio_path": str(audio_path)})
        except Exception as e:
            return StageResult.failure(STAGE_EXTRACT, e)

    async def _execute_transcribe(self) -> StageResult:
        """Execute the transcription stage."""
        try:
            asr_provider = create_asr_provider(self.config.asr_provider, self.config.asr_model)
            transcriber = Transcriber(
                asr_provider=asr_provider,
                output_dir=self.config.output_dir,
                cost_estimator=self.cost_estimator,
            )

            # Find audio path from checkpoint or default
            audio_path = self.config.output_dir / ".checkpoint" / "audio" / "audio.wav"
            if not audio_path.exists():
                # Try extract stage checkpoint
                extract_data = self.checkpoint_manager.load(STAGE_EXTRACT)
                if extract_data and "audio_path" in extract_data:
                    audio_path = Path(extract_data["audio_path"])

            transcript = await transcriber.transcribe(audio_path)

            self._emit(ProgressEvent(
                type=ProgressEventType.COST_UPDATE,
                stage=STAGE_TRANSCRIBE,
                cost_usd=self.cost_estimator.total_cost,
                budget_usd=self.config.max_budget_usd,
            ))

            # Check transcription confidence threshold
            if transcript.confidence < self.config.transcription_confidence_threshold:
                self._emit(ProgressEvent(
                    type=ProgressEventType.WARNING,
                    message=(
                        f"Transcription confidence {transcript.confidence:.2f} "
                        f"< {self.config.transcription_confidence_threshold} — review required"
                    ),
                ))

            return StageResult.success(STAGE_TRANSCRIBE, data={"transcript": transcript})
        except Exception as e:
            return StageResult.failure(STAGE_TRANSCRIBE, e)

    async def _execute_segment(self) -> StageResult:
        """Execute the segmentation stage."""
        try:
            llm_provider = create_llm_provider(self.config.llm_provider, self.config.llm_model)
            segmenter = ChapterSegmenter(
                llm_provider=llm_provider,
                confidence_threshold=self.config.segmentation_confidence_threshold,
            )

            # Load transcript from checkpoint
            asr_data = self.checkpoint_manager.load(STAGE_TRANSCRIBE)
            if asr_data is None:
                return StageResult.failure(
                    STAGE_SEGMENT,
                    ProviderError("No transcript checkpoint found — run transcribe stage first"),
                )

            transcript_text = asr_data.get("text", "")

            chapters = await segmenter.segment(
                transcript=transcript_text,
                video_title=self.config.input_video.stem,
                video_topic="",
                video_total_duration="00:00:00",
            )

            # Check segmentation confidence warnings
            for chapter in chapters:
                if chapter.confidence < self.config.segmentation_confidence_threshold:
                    self._emit(ProgressEvent(
                        type=ProgressEventType.WARNING,
                        message=(
                            f"Chapter '{chapter.title}' segmentation confidence "
                            f"{chapter.confidence:.2f} < {self.config.segmentation_confidence_threshold} threshold"
                        ),
                        chapter_slug=chapter.title.lower().replace(" ", "-"),
                    ))

            self._emit(ProgressEvent(
                type=ProgressEventType.COST_UPDATE,
                stage=STAGE_SEGMENT,
                cost_usd=self.cost_estimator.total_cost,
                budget_usd=self.config.max_budget_usd,
            ))

            return StageResult.success(STAGE_SEGMENT, data={"chapters": chapters})
        except Exception as e:
            return StageResult.failure(STAGE_SEGMENT, e)

    async def _execute_enrich(self) -> StageResult:
        """Execute the enrichment stage."""
        try:
            llm_provider = create_llm_provider(self.config.llm_provider, self.config.llm_model)
            enricher = MetadataEnricher(llm_provider=llm_provider)

            # Load chapters from checkpoint
            segment_data = self.checkpoint_manager.load(STAGE_SEGMENT)
            if segment_data is None:
                return StageResult.failure(
                    STAGE_ENRICH,
                    ProviderError("No chapters checkpoint found — run segment stage first"),
                )

            chapters_data = segment_data.get("chapters", [])
            chapters = [Chapter(**c) for c in chapters_data]
            enriched_chapters: List[EnrichedChapter] = []

            total_chapters = len(chapters)
            for i, chapter in enumerate(chapters):
                prev_title = chapters[i - 1].title if i > 0 else None
                next_title = chapters[i + 1].title if i < total_chapters - 1 else None

                enriched = await enricher.enrich(
                    chapter=chapter,
                    video_title=self.config.input_video.stem,
                    video_topic="",
                    video_total_duration="00:00:00",
                    total_chapters=total_chapters,
                    prev_chapter_title=prev_title,
                    next_chapter_title=next_title,
                )
                enriched_chapters.append(enriched)

            self._emit(ProgressEvent(
                type=ProgressEventType.COST_UPDATE,
                stage=STAGE_ENRICH,
                cost_usd=self.cost_estimator.total_cost,
                budget_usd=self.config.max_budget_usd,
            ))

            return StageResult.success(STAGE_ENRICH, data={"chapters": enriched_chapters})
        except Exception as e:
            return StageResult.failure(STAGE_ENRICH, e)

    async def _execute_materialize(self) -> StageResult:
        """Execute the materialization stage."""
        try:
            materializer = ChapterMaterializer(self.config.output_dir)

            # Load chapters from checkpoint (enrich or segment)
            enrich_data = self.checkpoint_manager.load(STAGE_ENRICH)
            if enrich_data:
                chapters_data = enrich_data.get("chapters", [])
                chapters = []
                for c in chapters_data:
                    if "chapter" in c:
                        # EnrichedChapter format
                        base = Chapter(**c["chapter"])
                        chapters.append(EnrichedChapter(
                            chapter=base,
                            description=c.get("description", ""),
                            context=c.get("context", ""),
                            summary_bullets=c.get("summary_bullets", []),
                            terms_used=c.get("terms_used", []),
                            key_concepts=c.get("key_concepts", []),
                            entities_detected=c.get("entities_detected", {}),
                            highlights=c.get("highlights", []),
                            pedagogy=c.get("pedagogy", {}),
                            confidence=c.get("confidence", {}),
                        ))
                    else:
                        chapters.append(Chapter(**c))
            else:
                segment_data = self.checkpoint_manager.load(STAGE_SEGMENT)
                if segment_data is None:
                    return StageResult.failure(
                        STAGE_MATERIALIZE,
                        ProviderError("No chapters checkpoint found"),
                    )
                chapters_data = segment_data.get("chapters", [])
                chapters = [Chapter(**c) for c in chapters_data]

            # Load transcript for SRT generation
            asr_data = self.checkpoint_manager.load(STAGE_TRANSCRIBE)
            words_data = []
            transcript_confidence = 0.0
            if asr_data:
                words_data = [WordTimestamp(**w) for w in asr_data.get("words", [])]
                transcript_confidence = asr_data.get("confidence", 0.0)

            transcript = TranscriptResult(
                text="",
                confidence=transcript_confidence,
                words=words_data,
                duration_s=0.0,
                provider="mock",
                model="mock",
            )

            source_video = self.config.input_video if self.config.input_video.exists() else None

            for chapter in chapters:
                materializer.materialize(
                    chapter=chapter,
                    transcript=transcript,
                    source_video=source_video,
                )
                self._emit(ProgressEvent(
                    type=ProgressEventType.CHAPTER_COMPLETE,
                    chapter_slug=chapter.title.lower().replace(" ", "-"),
                    chapter_number=chapter.number,
                    total_chapters=len(chapters),
                ))

            return StageResult.success(
                STAGE_MATERIALIZE,
                data={"chapters_dir": str(materializer.chapters_dir)},
            )
        except Exception as e:
            return StageResult.failure(STAGE_MATERIALIZE, e)

    def _find_resume_stage(self) -> int:
        """Determine which stage to resume from based on checkpoints.

        Returns:
            Zero-based index of the first stage to execute.
        """
        for i, stage_name in enumerate(STAGE_ORDER):
            if not self.checkpoint_manager.exists(stage_name):
                return i
        # All stages have checkpoints — restart from beginning
        return 0

    @staticmethod
    def _serialize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize data for JSON checkpoint storage.

        Converts Pydantic models to dicts recursively.

        Args:
            data: Dictionary that may contain Pydantic models.

        Returns:
            JSON-serializable dictionary.
        """
        result = {}
        for key, value in data.items():
            if hasattr(value, "model_dump"):
                result[key] = value.model_dump()
            elif isinstance(value, list):
                result[key] = [
                    item.model_dump() if hasattr(item, "model_dump") else item
                    for item in value
                ]
            else:
                result[key] = value
        return result
