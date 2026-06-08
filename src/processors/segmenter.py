"""Chapter segmentation using LLM prompt injection.

ChapterSegmenter takes a full transcript and uses an LLM to split it
into coherent chapter segments. PromptManager handles template loading
and variable injection.

Supports capability-aware processing: the segmenter automatically selects
the appropriate prompt template based on the ASR provider's capabilities.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.models.chapter import Chapter
from src.models.transcription import TranscriptResult, WordTimestamp
from src.processors.transcript_processor import (
    AdvancedTranscriptProcessor,
    BasicTranscriptProcessor,
    CleanTranscriptProcessor,
    TranscriptProcessor,
    select_processor,
)
from src.providers.asr.base import ProviderCapabilities
from src.providers.llm.base import LLMProvider
from src.utils.errors import ProviderError
from src.utils.json_extractor import extract_json_from_llm_response
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_MAX_RETRIES = 2


def _extract_json_from_response(response: str) -> List[Dict[str, Any]]:
    """Extract JSON array from LLM response text with robust parsing."""
    # Use the robust JSON extractor
    try:
        # First, try to parse as array directly
        parsed = extract_json_from_llm_response(response)
        if isinstance(parsed, list):
            return parsed
        else:
            # If it's a single object, wrap in array
            return [parsed]
    except Exception:
        # Fallback to original logic
        start = response.find("[")
        end = response.rfind("]")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("No JSON array found in response")
        
        json_str = response[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in response: {e}")


class PromptManager:
    """Manages LLM prompt templates with variable injection."""

    def __init__(self, prompts_dir: Path = None):
        """Initialize PromptManager.
        
        Args:
            prompts_dir: Directory containing prompt templates (default: ./prompts)
        """
        self.prompts_dir = prompts_dir or Path(__file__).parent.parent.parent / "prompts"
        self._cache = {}

    def load(self, filename: str) -> str:
        """Load prompt template from file."""
        if filename in self._cache:
            return self._cache[filename]
            
        prompt_path = self.prompts_dir / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_path}")
            
        content = prompt_path.read_text(encoding="utf-8")
        self._cache[filename] = content
        return content

    def inject(self, template: str, **kwargs) -> str:
        """Inject variables into prompt template."""
        result = template
        
        # Handle simple variable substitution
        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, ensure_ascii=False, indent=2)
            else:
                value_str = str(value)
            result = result.replace(placeholder, value_str)
            
        return result

    def load_and_inject(self, filename: str, **kwargs) -> str:
        """Load prompt template and inject variables in one step."""
        template = self.load(filename)
        return self.inject(template, **kwargs)


class ChapterSegmenter:
    """LLM-based chapter segmentation.

    Takes a full video transcript and uses an LLM to split it into
    coherent chapter segments with timing and confidence scores.

    Automatically selects the processing strategy based on provider capabilities:
    - Providers with word timestamps use the advanced prompt (segmenter.md)
    - Providers without word timestamps use the basic prompt (segmenter-basic.md)
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        prompt_manager: Optional[PromptManager] = None,
        prompt_filename: str = "segmenter.md",
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """Initialize ChapterSegmenter.

        Args:
            llm_provider: LLM provider for generating segmentations.
            prompt_manager: Prompt manager for loading templates.
            prompt_filename: Default filename of the segmenter prompt template.
            confidence_threshold: Minimum acceptable segmentation confidence.
            max_retries: Maximum retries for malformed LLM responses.
        """
        self.llm_provider = llm_provider
        self.prompt_manager = prompt_manager or PromptManager()
        self.prompt_filename = prompt_filename
        self.confidence_threshold = confidence_threshold
        self.max_retries = max_retries

    async def segment(
        self,
        transcript: TranscriptResult,
        video_title: str,
        video_topic: str,
        video_total_duration: str,
        asr_capabilities: Optional[ProviderCapabilities] = None,
    ) -> List[Chapter]:
        """Segment a transcript into chapters using LLM with optimized timing.
        
        Uses clean text for semantic analysis but applies real timing data
        during post-processing for precise chapter boundaries.

        Args:
            transcript: Full video transcript result.
            video_title: Title of the video.
            video_topic: General topic/subject of the video.
            video_total_duration: Total duration string (e.g. "00:30:00").
            asr_capabilities: Capabilities of the ASR provider (for processor selection).

        Returns:
            List of Chapter objects with real timing data applied.

        Raises:
            ProviderError: If LLM response cannot be parsed after retries.
        """
        # Select processor based on capabilities and actual transcript data
        processor = select_processor(asr_capabilities or ProviderCapabilities(), transcript)
        logger.info(f"ChapterSegmenter using processor: {processor.__class__.__name__}")
        
        # Prepare the transcript text (applies preprocessing)
        prepared_text = processor.prepare_transcript_text(transcript)
        logger.info(f"Prepared transcript length: {len(prepared_text)} characters")
        logger.info(f"First 200 chars of prepared text: {prepared_text[:200]}")
        
        # Build the prompt with clean text (no technical timing details)
        prompt_kwargs = {
            "VIDEO_TITLE": video_title,
            "VIDEO_TOPIC": video_topic,
            "VIDEO_TOTAL_DURATION": video_total_duration,
            "FULL_TRANSCRIPT": prepared_text,
        }
            
        prompt = self.prompt_manager.load_and_inject(
            processor.get_prompt_filename(),
            **prompt_kwargs
        )

        # Call LLM with retry logic
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = await self.llm_provider.generate(
                    prompt=prompt,
                    response_format="json",
                )

                chapters = self._parse_response(response.text)
                return self._apply_confidence_flags(chapters)

            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                last_error = e
                logger.warning(
                    "Segmentation parse error (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    str(e),
                )
                continue

        raise ProviderError(
            f"Failed to parse LLM segmentation after {self.max_retries} retries: {last_error}"
        )

    def _parse_response(self, response: str) -> List[Chapter]:
        """Parse LLM response into Chapter objects."""
        raw_chapters = _extract_json_from_response(response)
        chapters = []
        for raw in raw_chapters:
            chapters.append(Chapter(**raw))
        return chapters

    def _apply_confidence_flags(self, chapters: List[Chapter]) -> List[Chapter]:
        """Apply confidence-based review flags to chapters."""
        for chapter in chapters:
            if chapter.confidence < self.confidence_threshold:
                chapter.needs_review = True
                logger.warning(
                    "Chapter %d '%s' has low confidence (%.2f < %.2f) — needs review",
                    chapter.number,
                    chapter.title,
                    chapter.confidence,
                    self.confidence_threshold,
                )
        return chapters