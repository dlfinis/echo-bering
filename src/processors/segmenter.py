"""Chapter segmentation using LLM prompt injection.

ChapterSegmenter takes a full transcript and uses an LLM to split it
into coherent chapter segments. PromptManager handles template loading
and variable injection.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.models.chapter import Chapter
from src.providers.llm.base import LLMProvider
from src.utils.errors import ProviderError
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_MAX_RETRIES = 3


def _check_needs_review(confidence: float, threshold: float) -> bool:
    """Determine if a chapter needs human review based on confidence.

    Args:
        confidence: Segmentation confidence score (0-1).
        threshold: Minimum acceptable confidence.

    Returns:
        True if confidence is below threshold.
    """
    return confidence < threshold


def _extract_json_from_response(text: str) -> Any:
    """Extract JSON from LLM response text.

    Handles cases where the LLM wraps JSON in markdown code blocks
    or adds explanatory text around the JSON.

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed JSON object.

    Raises:
        json.JSONDecodeError: If no valid JSON found.
    """
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in markdown code blocks
    if "```" in text:
        # Extract content between ``` markers
        start = text.find("```")
        # Skip language identifier if present
        after_start = text.index("\n", start + 3) if "\n" in text[start:start+20] else start + 3
        end = text.find("```", after_start)
        if end > after_start:
            json_text = text[after_start:end].strip()
            return json.loads(json_text)

    # Try to find JSON array or object boundaries
    if text.strip().startswith("["):
        # Find matching closing bracket
        depth = 0
        for i, char in enumerate(text):
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return json.loads(text[:i+1])

    if text.strip().startswith("{"):
        # Find matching closing brace
        depth = 0
        for i, char in enumerate(text):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[:i+1])

    # Last resort: re-raise the original error
    return json.loads(text)


class PromptManager:
    """Load and inject variables into prompt templates.

    Prompts are loaded from the prompts directory and cached for
    performance. Variables use {{VARIABLE_NAME}} syntax.
    """

    def __init__(self, prompt_dir: Optional[Path] = None):
        """Initialize PromptManager.

        Args:
            prompt_dir: Directory containing prompt files. Defaults to project prompts dir.
        """
        if prompt_dir is None:
            prompt_dir = Path(__file__).parent.parent.parent / "prompts"
        self.prompt_dir = prompt_dir
        self._cache: Dict[str, str] = {}

    def load(self, filename: str) -> str:
        """Load a prompt template from file.

        Args:
            filename: Prompt filename relative to prompt_dir.

        Returns:
            Prompt template text.

        Raises:
            FileNotFoundError: If prompt file does not exist.
        """
        if filename in self._cache:
            return self._cache[filename]

        filepath = self.prompt_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Prompt file not found: {filepath}")

        content = filepath.read_text(encoding="utf-8")
        self._cache[filename] = content
        return content

    def load_and_inject(self, filename: str, **variables: str) -> str:
        """Load a prompt and inject template variables.

        Args:
            filename: Prompt filename relative to prompt_dir.
            **variables: Key-value pairs for template injection.

        Returns:
            Prompt text with variables substituted.
        """
        template = self.load(filename)
        return self.inject(template, **variables)

    def inject(self, template: str, **variables: str) -> str:
        """Inject variables into a template string.

        Args:
            template: Template with {{VARIABLE_NAME}} placeholders.
            **variables: Key-value pairs for substitution.

        Returns:
            Template with variables substituted. Missing variables are left as-is.
        """
        result = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value))
        return result

    def clear_cache(self) -> None:
        """Clear the prompt cache."""
        self._cache.clear()


class ChapterSegmenter:
    """LLM-based chapter segmentation.

    Takes a full video transcript and uses an LLM to split it into
    coherent chapter segments with timing and confidence scores.
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
            prompt_filename: Filename of the segmenter prompt template.
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
        transcript: str,
        video_title: str,
        video_topic: str,
        video_total_duration: str,
    ) -> List[Chapter]:
        """Segment a transcript into chapters using LLM.

        Args:
            transcript: Full video transcript text.
            video_title: Title of the video.
            video_topic: General topic/subject of the video.
            video_total_duration: Total duration string (e.g. "00:30:00").

        Returns:
            List of Chapter objects parsed from LLM response.

        Raises:
            ProviderError: If LLM response cannot be parsed after retries.
        """
        # Build the prompt with injected variables
        prompt = self.prompt_manager.load_and_inject(
            self.prompt_filename,
            VIDEO_TITLE=video_title,
            VIDEO_TOPIC=video_topic,
            VIDEO_TOTAL_DURATION=video_total_duration,
            FULL_TRANSCRIPT=transcript,
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

    def _parse_response(self, text: str) -> List[Chapter]:
        """Parse LLM response text into Chapter objects.

        Args:
            text: Raw LLM response text.

        Returns:
            List of Chapter objects.

        Raises:
            json.JSONDecodeError: If response is not valid JSON.
            ValueError: If parsed data does not match expected structure.
        """
        data = _extract_json_from_response(text)

        if not isinstance(data, list):
            raise ValueError(f"Expected JSON array of chapters, got {type(data).__name__}")

        chapters = []
        for i, item in enumerate(data):
            try:
                chapter = Chapter(**item)
                chapters.append(chapter)
            except Exception as e:
                raise ValueError(f"Invalid chapter data at index {i}: {e}") from e

        if not chapters:
            raise ValueError("LLM returned empty chapter list")

        logger.info("Parsed %d chapters from LLM response", len(chapters))
        return chapters

    def _apply_confidence_flags(self, chapters: List[Chapter]) -> List[Chapter]:
        """Apply needs_review flags based on confidence thresholds.

        Args:
            chapters: List of Chapter objects.

        Returns:
            Same list with needs_review flags set.
        """
        for chapter in chapters:
            chapter.needs_review = _check_needs_review(
                chapter.confidence, self.confidence_threshold
            )
            if chapter.needs_review:
                logger.warning(
                    "Chapter %d '%s' has low confidence (%.2f < %.2f) — needs review",
                    chapter.number,
                    chapter.title,
                    chapter.confidence,
                    self.confidence_threshold,
                )
        return chapters
