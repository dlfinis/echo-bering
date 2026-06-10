"""Chapter metadata enrichment using LLM prompt injection.

MetadataEnricher takes a segmented chapter and its transcript, then uses
an LLM to generate enriched metadata including descriptions, knowledge
extraction, highlights, and pedagogical analysis.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from src.models.chapter import Chapter, EnrichedChapter
from src.processors.segmenter import PromptManager
from src.providers.llm.base import LLMProvider
from src.utils.errors import ProviderError
from src.utils.json_extractor import extract_json_from_llm_response
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_RETRIES = 3


class MetadataEnricher:
    """LLM-based chapter metadata enrichment.

    Takes a Chapter with transcript and generates enriched metadata
    including descriptions, knowledge extraction, highlights, and
    pedagogical analysis.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        prompt_manager: Optional[PromptManager] = None,
        prompt_filename: str = "enricher.md",
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """Initialize MetadataEnricher.

        Args:
            llm_provider: LLM provider for generating enrichments.
            prompt_manager: Prompt manager for loading templates.
            prompt_filename: Filename of the enricher prompt template.
            max_retries: Maximum retries for malformed LLM responses.
        """
        self.llm_provider = llm_provider
        self.prompt_manager = prompt_manager or PromptManager()
        self.prompt_filename = prompt_filename
        self.max_retries = max_retries

    async def enrich(
        self,
        chapter: Chapter,
        video_title: str,
        video_topic: str,
        video_total_duration: str,
        total_chapters: int,
        prev_chapter_title: Optional[str] = None,
        next_chapter_title: Optional[str] = None,
    ) -> EnrichedChapter:
        """Enrich a chapter with metadata using LLM.

        Args:
            chapter: Chapter to enrich with transcript and timing.
            video_title: Title of the video.
            video_topic: General topic of the video.
            video_total_duration: Total duration string (e.g. "00:30:00").
            total_chapters: Total number of chapters in the video.
            prev_chapter_title: Title of the previous chapter (None if first).
            next_chapter_title: Title of the next chapter (None if last).

        Returns:
            EnrichedChapter with full metadata.

        Raises:
            ProviderError: If LLM response cannot be parsed after retries.
        """
        # Build prompt with all context variables
        prompt = self.prompt_manager.load_and_inject(
            self.prompt_filename,
            VIDEO_TITLE=video_title,
            VIDEO_TOPIC=video_topic,
            VIDEO_TOTAL_DURATION=video_total_duration,
            CHAPTER_NUMBER=str(chapter.number),
            TOTAL_CHAPTERS=str(total_chapters),
            CHAPTER_START=chapter.start_time,
            CHAPTER_END=chapter.end_time,
            PREV_CHAPTER_TITLE=prev_chapter_title or "N/A",
            NEXT_CHAPTER_TITLE=next_chapter_title or "N/A",
            CHAPTER_TRANSCRIPT=chapter.transcript,
        )

        # Call LLM with retry logic
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = await self.llm_provider.generate(
                    prompt=prompt,
                    response_format="json",
                )

                enriched = self._parse_response(response.text, chapter)
                return enriched

            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                last_error = e
                logger.warning(
                    "Enrichment parse error (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    str(e),
                )
                continue

        raise ProviderError(
            f"Failed to parse LLM enrichment after {self.max_retries} retries: {last_error}"
        )

    def _parse_response(self, text: str, chapter: Chapter) -> EnrichedChapter:
        """Parse LLM response into EnrichedChapter.

        Args:
            text: Raw LLM response text.
            chapter: Original chapter to attach to enriched data.

        Returns:
            EnrichedChapter with all metadata fields.

        Raises:
            json.JSONDecodeError: If response is not valid JSON.
            ValueError: If parsed data does not match expected structure.
        """
        data = extract_json_from_llm_response(text)

        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object for enrichment, got {type(data).__name__}")

        # Validate required top-level keys
        required_keys = {"chapter", "content", "knowledge", "highlights", "pedagogy", "confidence"}
        missing = required_keys - set(data.keys())
        if missing:
            raise ValueError(f"Enrichment missing required keys: {missing}")

        # Build highlights from raw data
        highlights_data = data.get("highlights", [])
        highlights = []
        for h in highlights_data:
            try:
                highlights.append(
                    {
                        "timestamp": h.get("timestamp", ""),
                        "type": h.get("type", "insight"),
                        "label": h.get("label", ""),
                        "quote": h.get("quote", ""),
                        "importance": h.get("importance", "media"),
                    }
                )
            except Exception as e:
                logger.warning("Skipping invalid highlight: %s", e)

        # Build EnrichedChapter
        enriched = EnrichedChapter(
            chapter=chapter,
            description=data["content"].get("description", ""),
            context=data["content"].get("context", ""),
            summary_bullets=data["content"].get("summary_bullets", []),
            terms_used=data["knowledge"].get("terms_used", []),
            key_concepts=data["knowledge"].get("key_concepts", []),
            entities_detected=data["knowledge"].get("entities_detected", {}),
            highlights=highlights,
            pedagogy=data.get("pedagogy", {}),
            confidence=data.get("confidence", {}),
        )

        # Apply needs_review flag from enrichment confidence
        enrichment_confidence = data.get("confidence", {})
        if enrichment_confidence.get("needs_review"):
            logger.warning(
                "Chapter %d '%s' enrichment flagged for review: %s",
                chapter.number,
                chapter.title,
                enrichment_confidence.get("review_reasons", []),
            )

        logger.info("Enriched chapter %d '%s' successfully", chapter.number, chapter.title)
        return enriched
