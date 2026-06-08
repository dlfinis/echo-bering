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
from src.models.transcription import WordTimestamp
from src.providers.asr.base import TranscriptResult
from src.providers.factory import create_asr_provider, create_llm_provider
from src.utils.checkpoint import CheckpointManager
from src.utils.cost_estimator import CostEstimator
from src.utils.errors import BudgetError, CapabilityError, ProviderError
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


from src.orchestrators.utils import _format_duration, generate_project_name
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
        
        # Generate project name and set final output directory
        if config.project_name:
            project_dir = config.output_dir / config.project_name
        else:
            # Get existing projects in output directory
            existing_projects = set()
            if config.output_dir.exists():
                existing_projects = {d.name for d in config.output_dir.iterdir() if d.is_dir()}
            
            project_name = generate_project_name(config, existing_projects)
            project_dir = config.output_dir / project_name
            
        self.project_dir = project_dir
        self.progress_callback = progress_callback
        self.cost_estimator = CostEstimator()
        self.checkpoint_manager = CheckpointManager(project_dir)
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

        # Clean up checkpoints on success if not keeping them
        if not self.config.keep_checkpoints:
            self.checkpoint_manager.clear()
            logger.debug("Checkpoints cleared (keep_checkpoints=False)")
        else:
            logger.debug("Checkpoints preserved for debugging (keep_checkpoints=True)")
        
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
            extractor = AudioExtractor(self.project_dir)
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
            # Pre-flight validation for provider credentials and constraints
            await self._validate_provider_setup()
            
            asr_provider = create_asr_provider(
                self.config.asr_provider,
                self.config.asr_model,
                required_features=self.config.required_asr_features,
                request_delay_seconds=getattr(self.config, 'groq_request_delay_seconds', 0.0) if self.config.asr_provider == 'groq' else getattr(self.config, 'assemblyai_request_delay_seconds', 0.0),
                hf_token=getattr(self.config, 'hf_token', None),
            )
            
            # Find audio path from checkpoint or default
            audio_path = self.project_dir / ".checkpoint" / "audio" / "audio.wav"
            if not audio_path.exists():
                # Try extract stage checkpoint
                extract_data = self.checkpoint_manager.load(STAGE_EXTRACT)
                if extract_data and "audio_path" in extract_data:
                    audio_path = Path(extract_data["audio_path"])

            # Determine if this is a long video that needs chunked processing
            is_long_video = self._is_long_video(audio_path)
            
            if is_long_video:
                # Use chunked processing for long videos
                logger.info("Long video detected, using chunked processing: %s", audio_path)
                
                # Determine optimal chunk duration based on provider
                chunk_duration_minutes = self._get_optimal_chunk_duration(self.config.asr_provider)
                
                from src.processors.chunking import TimedChunkingStrategy
                chunking_strategy = TimedChunkingStrategy(
                    chunk_duration_min=chunk_duration_minutes,
                    overlap_s=self.config.chunk_overlap_seconds
                )
                
                transcriber = Transcriber(
                    asr_provider=asr_provider,
                    output_dir=self.project_dir,
                    cost_estimator=self.cost_estimator,
                    chunking_strategy=chunking_strategy,
                )
            else:
                # Use standard processing for short videos (backward compatibility)
                logger.info("Standard video detected, using normal processing: %s", audio_path)
                transcriber = Transcriber(
                    asr_provider=asr_provider,
                    output_dir=self.project_dir,
                    cost_estimator=self.cost_estimator,
                )

            transcript_result = await transcriber.transcribe(audio_path)

            self._emit(ProgressEvent(
                type=ProgressEventType.COST_UPDATE,
                stage=STAGE_TRANSCRIBE,
                cost_usd=self.cost_estimator.total_cost,
                budget_usd=self.config.max_budget_usd,
            ))

            return StageResult.success(STAGE_TRANSCRIBE, data={"transcript": transcript_result})
        except CapabilityError:
            raise
        except Exception as e:
            return StageResult.failure(STAGE_TRANSCRIBE, e)

    def _is_long_video(self, audio_path: Path) -> bool:
        """Determine if video is long enough to require chunked processing.
        
        Args:
            audio_path: Path to the audio file.
            
        Returns:
            True if video meets criteria for chunked processing.
        """
        if not audio_path.exists():
            return False
        
        # Check file size (>25MB for Groq free tier)
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 25:
            logger.info("Video flagged as long due to size: %.2f MB > 25 MB", file_size_mb)
            return True
        
        # Check duration (>30 minutes)
        duration_s = self._get_audio_duration(audio_path)
        duration_min = duration_s / 60
        if duration_min > 30:
            logger.info("Video flagged as long due to duration: %.2f min > 30 min", duration_min)
            return True
            
        return False

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration using ffprobe.
        
        Args:
            audio_path: Path to the audio file.
            
        Returns:
            Duration in seconds, or 0.0 if unable to determine.
        """
        import subprocess

        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError) as e:
            logger.debug("Could not determine audio duration: %s", e)

        return 0.0

    def _get_optimal_chunk_duration(self, provider: str) -> int:
        """Get optimal chunk duration based on provider constraints.
        
        Args:
            provider: ASR provider name.
            
        Returns:
            Optimal chunk duration in minutes.
        """
        # Provider-specific optimal durations based on constraints
        provider_durations = {
            "groq": 8,      # Conservative for 25MB limit
            "assemblyai": 30,  # Can handle longer chunks
            "openai": 25,   # Moderate duration
            "mlx": 20,      # Local processing, balance memory/performance
        }
        
        duration = provider_durations.get(provider, 20)
        logger.info("Using optimal chunk duration for %s: %d minutes", provider, duration)
        return duration

    async def _validate_provider_setup(self):
        """Validate provider credentials and configuration before processing.
        
        Checks that provider-specific requirements are met before starting processing.
        """
        # Validate Groq provider setup
        if self.config.asr_provider == "groq":
            # Check for Groq API key
            import os
            groq_api_key = os.getenv("GROQ_API_KEY")
            if not groq_api_key:
                logger.warning("GROQ_API_KEY environment variable not set - Groq requests may fail")
        
        # Validate AssemblyAI provider setup
        elif self.config.asr_provider == "assemblyai":
            import os
            aai_api_key = os.getenv("ASSEMBLYAI_API_KEY")
            if not aai_api_key:
                logger.warning("ASSEMBLYAI_API_KEY environment variable not set - AssemblyAI requests may fail")
        
        # Validate OpenAI provider setup
        elif self.config.asr_provider == "openai":
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                logger.warning("OPENAI_API_KEY environment variable not set - OpenAI requests may fail")
        
        # Validate MLX-Whisper provider setup
        elif self.config.asr_provider in ["mlx", "mlx-whisper"]:
            if self.config.asr_model in ["large-v3"] and not getattr(self.config, 'hf_token', None):
                logger.warning(
                    "Using mlx-whisper with large-v3 model but no HF_TOKEN provided. "
                    "May encounter authentication issues with private models."
                )
        
        logger.info(f"Provider {self.config.asr_provider} pre-flight validation completed")

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

            # Reconstruct TranscriptResult object
            transcript_dict = asr_data.get("transcript", {})
            if isinstance(transcript_dict, dict):
                transcript_result = TranscriptResult(**transcript_dict)
            else:
                # Handle legacy format (just text)
                transcript_result = TranscriptResult(
                    text=str(transcript_dict),
                    confidence=1.0,
                    words=[],
                    segments=[],
                    duration_s=0.0,
                    provider="unknown",
                    model="unknown"
                )

            # Get ASR provider to access capabilities
            asr_provider = create_asr_provider(self.config.asr_provider, self.config.asr_model)
            
            chapters = await segmenter.segment(
                transcript=transcript_result,
                video_title=self.config.input_video.stem,
                video_topic="",
                video_total_duration=_format_duration(transcript_result.duration_s) if transcript_result.duration_s > 0 else "00:00:00",
                asr_capabilities=asr_provider.capabilities,
            )

            self.checkpoint_manager.save(STAGE_SEGMENT, {"chapters": [c.model_dump() for c in chapters]})
            logger.info("Segmentation completed successfully with %d chapters", len(chapters))
            return StageResult.success(STAGE_SEGMENT, data={"chapters": chapters})

        except CapabilityError:
            raise
        except Exception as e:
            logger.exception("Segmentation stage failed")
            return StageResult.failure(STAGE_SEGMENT, e)

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
            materializer = ChapterMaterializer(self.project_dir)

            # Load segment data first to get transcripts
            segment_data = self.checkpoint_manager.load(STAGE_SEGMENT)
            segment_transcripts = {}
            if segment_data:
                for c in segment_data.get("chapters", []):
                    chapter_num = c.get("number")
                    if chapter_num is not None:
                        segment_transcripts[chapter_num] = c.get("transcript", "")

            # Load chapters from checkpoint (enrich or segment)
            enrich_data = self.checkpoint_manager.load(STAGE_ENRICH)
            if enrich_data:
                chapters_data = enrich_data.get("chapters", [])
                chapters = []
                for c in chapters_data:
                    if "chapter" in c:
                        # EnrichedChapter format - need to combine chapter + timing data
                        chapter_base = c["chapter"]
                        timing_data = c.get("timing", {})
                        
                        # Parse time strings to seconds
                        def parse_time_to_seconds(time_str: str) -> float:
                            """Convert HH:MM:SS.mmm to seconds."""
                            if not time_str or time_str == "00:00:00.000":
                                return 0.0
                            try:
                                h, m, s = time_str.split(':')
                                return int(h) * 3600 + int(m) * 60 + float(s)
                            except (ValueError, AttributeError):
                                return 0.0
                        
                        start_seconds = parse_time_to_seconds(timing_data.get("start_time", "00:00:00.000"))
                        end_seconds = parse_time_to_seconds(timing_data.get("end_time", "00:00:00.000"))
                        
                        # Get transcript from segment data
                        chapter_num = chapter_base.get("number", 0)
                        transcript_text = segment_transcripts.get(chapter_num, "")
                        
                        # Create Chapter with all required fields
                        chapter_obj = Chapter(
                            number=chapter_num,
                            title=chapter_base.get("title", ""),
                            start_time=timing_data.get("start_time", "00:00:00.000"),
                            end_time=timing_data.get("end_time", "00:00:00.000"),
                            start_seconds=start_seconds,
                            end_seconds=end_seconds,
                            confidence=c.get("confidence", {}).get("segmentation_score", 0.8),
                            transcript=transcript_text,  # Fill from segment checkpoint
                            needs_review=c.get("confidence", {}).get("needs_review", False)
                        )
                        chapters.append(EnrichedChapter(
                            chapter=chapter_obj,
                            description=c.get("content", {}).get("description", ""),
                            context=c.get("content", {}).get("context", ""),
                            summary_bullets=c.get("content", {}).get("summary_bullets", []),
                            terms_used=c.get("knowledge", {}).get("terms_used", []),
                            key_concepts=c.get("knowledge", {}).get("key_concepts", []),
                            entities_detected=c.get("knowledge", {}).get("entities_detected", {}),
                            highlights=c.get("highlights", []),
                            pedagogy=c.get("pedagogy", {}),
                            confidence=c.get("confidence", {}),
                        ))
                    else:
                        chapters.append(Chapter(**c))
            else:
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
                # Handle both direct TranscriptResult and nested format from different providers
                if "transcript" in asr_data and isinstance(asr_data["transcript"], dict):
                    # Nested format: {"transcript": {TranscriptResult}}
                    transcript_dict = asr_data["transcript"]
                else:
                    # Direct format: {TranscriptResult}
                    transcript_dict = asr_data
                    
                words_data = [WordTimestamp(**w) for w in transcript_dict.get("words", [])]
                transcript_confidence = transcript_dict.get("confidence", 0.0)

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
                # Handle both Chapter and EnrichedChapter objects
                if hasattr(chapter, 'chapter'):
                    # EnrichedChapter
                    chapter_title = chapter.chapter.title
                    chapter_number = chapter.chapter.number
                else:
                    # Chapter
                    chapter_title = chapter.title
                    chapter_number = chapter.number
                    
                self._emit(ProgressEvent(
                    type=ProgressEventType.CHAPTER_COMPLETE,
                    chapter_slug=chapter_title.lower().replace(" ", "-"),
                    chapter_number=chapter_number,
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
        # All stages have checkpoints — pipeline already completed
        return len(STAGE_ORDER)

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
