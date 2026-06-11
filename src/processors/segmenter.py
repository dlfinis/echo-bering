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


def _format_seconds_as_hms(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


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
        preferred_chapters: Optional[int] = None,
    ):
        """Initialize ChapterSegmenter.

        Args:
            llm_provider: LLM provider for generating segmentations.
            prompt_manager: Prompt manager for loading templates.
            prompt_filename: Default filename of the segmenter prompt template.
            confidence_threshold: Minimum acceptable segmentation confidence.
            max_retries: Maximum retries for malformed LLM responses.
            preferred_chapters: Target number of chapters. The LLM treats this as a
                recommendation, not a hard cap — it can produce fewer if the content
                has fewer natural themes, but should not exceed it by more than ~20%.
        """
        self.llm_provider = llm_provider
        self.prompt_manager = prompt_manager or PromptManager()
        self.prompt_filename = prompt_filename
        self.confidence_threshold = confidence_threshold
        self.max_retries = max_retries
        self.preferred_chapters = preferred_chapters

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
        
        For long transcripts (>30k characters), uses hierarchical segmentation
        to process the transcript in manageable blocks.

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
        
        # For long transcripts with a user-defined target, prefer a single-pass
        # segmentation so the LLM can group chapters thematically across the whole video.
        # Hierarchical segmentation (block-based) is kept as a fallback when no
        # preferred_chapters is provided OR the transcript is extremely large.
        long_threshold = 30000
        very_long_threshold = 120000  # ~2h of transcript prepared text

        if len(prepared_text) > long_threshold and (
            self.preferred_chapters is None or len(prepared_text) > very_long_threshold
        ):
            logger.info(
                "Long transcript detected (%d chars) and no preferred_chapters or very long, "
                "using hierarchical segmentation",
                len(prepared_text),
            )
            return await self._segment_hierarchical(
                prepared_text, transcript, video_title, video_topic, video_total_duration, processor
            )

        if len(prepared_text) > long_threshold and self.preferred_chapters is not None:
            logger.info(
                "Long transcript detected (%d chars) BUT preferred_chapters=%d is set; "
                "using single-pass segmentation to preserve thematic grouping",
                len(prepared_text),
                self.preferred_chapters,
            )

        # Single-pass segmentation (short, long-with-target, or very-long fallback above)
        return await self._segment_standard(
            prepared_text, transcript, video_title, video_topic, video_total_duration, processor
        )

    async def _segment_standard(
        self,
        prepared_text: str,
        transcript: TranscriptResult,
        video_title: str,
        video_topic: str,
        video_total_duration: str,
        processor: TranscriptProcessor,
    ) -> List[Chapter]:
        """Standard segmentation for shorter transcripts."""
        # Build the prompt with clean text (no technical timing details)
        prompt_kwargs = {
            "VIDEO_TITLE": video_title,
            "VIDEO_TOPIC": video_topic,
            "VIDEO_TOTAL_DURATION": video_total_duration,
            "FULL_TRANSCRIPT": prepared_text,
        }

        if self.preferred_chapters is not None:
            prompt_kwargs["PREFERRED_CHAPTERS"] = self.preferred_chapters

        prompt = self.prompt_manager.load_and_inject(
            processor.get_prompt_filename(),
            **prompt_kwargs
        )

        # Pre-render the new {{...}} blocks for preferred_chapters guidance.
        # These aren't simple variable substitutions — they're conditional sections
        # the LLM should see only when preferred_chapters is set.
        prompt = self._render_chapter_guidance(prompt, video_total_duration)

        # Call LLM with retry logic
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = await self.llm_provider.generate(
                    prompt=prompt,
                    response_format="json",
                )

                # Debug: log raw LLM response so we can see what the model actually
                # returned (helps diagnose cases where the LLM collapses everything
                # into 1 chapter, or where the response was truncated).
                usage = getattr(response, "usage", None) or {}
                logger.info(
                    "LLM response received: %d chars, tokens(prompt=%s completion=%s total=%s). First 300: %s",
                    len(response.text or ""),
                    usage.get("prompt_tokens"),
                    usage.get("completion_tokens"),
                    usage.get("total_tokens"),
                    (response.text or "")[:300],
                )

                chapters = self._parse_response(response.text)
                # Assign transcript text per chapter from the original ASR data
                # (not from the LLM response — the LLM prompt tells the model NOT
                # to include the transcript, to avoid max_tokens truncation).
                chapters = self._assign_transcripts(chapters, transcript, prepared_text)
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

    async def _segment_hierarchical(
        self,
        prepared_text: str,
        transcript: TranscriptResult,
        video_title: str,
        video_topic: str,
        video_total_duration: str,
        processor: TranscriptProcessor,
    ) -> List[Chapter]:
        """Hierarchical segmentation for long transcripts.
        
        Divides the transcript into manageable blocks (~20k chars each),
        processes each block independently, then consolidates the results.
        
        Args:
            prepared_text: Preprocessed transcript text.
            transcript: Full transcript result (for duration info).
            video_title: Video title.
            video_topic: Video topic.
            video_total_duration: Total duration string.
            processor: Transcript processor instance.
            
        Returns:
            Consolidated list of Chapter objects.
        """
        # Split transcript into blocks of ~20k characters
        block_size = 20000
        blocks = []
        for i in range(0, len(prepared_text), block_size):
            blocks.append(prepared_text[i:i+block_size])
        
        logger.info(f"Split transcript into {len(blocks)} blocks for hierarchical processing")
        
        all_chapters = []
        chapter_number = 1
        
        # Process each block
        for block_idx, block_text in enumerate(blocks, 1):
            logger.info(f"Processing block {block_idx}/{len(blocks)} ({len(block_text)} chars)")
            
            # Calculate approximate time range for this block
            chars_per_second = len(prepared_text) / transcript.duration_s if transcript.duration_s > 0 else 15
            block_start_char = (block_idx - 1) * block_size
            block_end_char = min(block_idx * block_size, len(prepared_text))
            
            block_start_seconds = block_start_char / chars_per_second
            block_end_seconds = block_end_char / chars_per_second
            
            # Convert to duration string for this block
            def format_duration(seconds):
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = seconds % 60
                return f"{h:02d}:{m:02d}:{s:06.3f}"
            
            block_duration = format_duration(block_end_seconds - block_start_seconds)
            
            # Adjust chapter numbering instruction for this block
            block_title = f"{video_title} (Parte {block_idx} de {len(blocks)})"
            
            try:
                # Process this block — pass the global target so each block is
                # proportional (preferred/total_blocks) when in hierarchical mode.
                block_target = None
                if self.preferred_chapters is not None:
                    block_target = max(1, round(self.preferred_chapters / len(blocks)))
                    logger.info(
                        "Block %d target chapters: %d (preferred=%d / %d blocks)",
                        block_idx, block_target, self.preferred_chapters, len(blocks),
                    )
                # Temporarily swap preferred_chapters for the per-block target
                original_target = self.preferred_chapters
                self.preferred_chapters = block_target
                try:
                    block_chapters = await self._segment_standard(
                        block_text,
                        transcript,
                        block_title,
                        video_topic,
                        block_duration,
                        processor
                    )
                finally:
                    self.preferred_chapters = original_target
                
                # Adjust timestamps and chapter numbers
                for chapter in block_chapters:
                    # Adjust timestamps to absolute positions
                    chapter.start_seconds += block_start_seconds
                    chapter.end_seconds += block_start_seconds
                    
                    # Convert back to time format
                    chapter.start_time = format_duration(chapter.start_seconds)
                    chapter.end_time = format_duration(chapter.end_seconds)
                    
                    # Update chapter number
                    chapter.number = chapter_number
                    chapter_number += 1
                    
                    all_chapters.append(chapter)
                
                logger.info(f"Block {block_idx} generated {len(block_chapters)} chapters")
                
            except Exception as e:
                logger.error(f"Failed to process block {block_idx}: {e}")
                # Continue with other blocks
                continue
        
        if not all_chapters:
            raise ProviderError("Hierarchical segmentation failed: no chapters generated from any block")
        
        logger.info(f"Hierarchical segmentation completed: {len(all_chapters)} total chapters")
        return self._apply_confidence_flags(all_chapters)

    def _parse_response(self, response: str) -> List[Chapter]:
        """Parse LLM response into Chapter objects.

        Transcript is intentionally NOT read from the LLM response — we
        assign it later from the original ASR data via _assign_transcripts.
        This avoids max_tokens truncation when the LLM tries to repeat the
        full transcript in each chapter.
        """
        raw_chapters = _extract_json_from_response(response)
        chapters = []
        for raw in raw_chapters:
            # Strip any 'transcript' key the LLM may have included — we ignore it
            raw.pop("transcript", None)
            # Default transcript to empty string; will be filled by _assign_transcripts
            raw.setdefault("transcript", "")
            try:
                chapters.append(Chapter(**raw))
            except Exception as e:
                logger.warning("Skipping malformed chapter from LLM: %s — %s", raw, e)
        return self._sanitize_chapters(chapters)

    @staticmethod
    def _sanitize_chapters(chapters: List[Chapter], min_duration_s: float = 5.0) -> List[Chapter]:
        """Drop empty/zero-length chapters and renumber sequentially.

        LLMs sometimes return a final "summary/wrap-up" chapter with
        end_seconds == start_seconds, which breaks ffmpeg and adds no value.
        We drop any chapter shorter than `min_duration_s` and renumber the rest.
        Note: we DO NOT check the transcript field here because the LLM is no
        longer providing transcripts (they're assigned after parsing).
        """
        sanitized: List[Chapter] = []
        for ch in chapters:
            duration = ch.end_seconds - ch.start_seconds
            if duration < min_duration_s:
                logger.warning(
                    "Dropping empty chapter #%d '%s' (duration=%.1fs)",
                    ch.number, ch.title, duration,
                )
                continue
            sanitized.append(ch)

        # Renumber sequentially from 1 to avoid gaps after dropping chapters.
        for idx, ch in enumerate(sanitized, 1):
            ch.number = idx
        return sanitized

    @staticmethod
    def _assign_transcripts(
        chapters: List[Chapter],
        transcript: TranscriptResult,
        prepared_text: str,
    ) -> List[Chapter]:
        """Assign transcript text to each chapter from the original ASR result.

        Uses the ASR's word-level timestamps (when available) to slice the
        transcript text per chapter. Falls back to character proportional
        slicing if word timestamps are missing.

        Also handles the case where the LLM produced an end_seconds slightly
        beyond the actual video duration (clamped to transcript length).
        """
        duration = transcript.duration_s or 0.0
        words = transcript.words or []
        has_word_ts = len(words) > 0

        # First pass: clamp all chapter timestamps to [0, duration]
        if duration > 0:
            for ch in chapters:
                if ch.start_seconds < 0:
                    ch.start_seconds = 0
                if ch.end_seconds > duration:
                    logger.warning(
                        "Clamping chapter '%s' end_seconds %.1f -> %.1f (video duration)",
                        ch.title, ch.end_seconds, duration,
                    )
                    ch.end_seconds = duration
                    ch.end_time = _format_seconds_as_hms(ch.end_seconds)

        # Second pass: assign transcripts
        for ch in chapters:
            if has_word_ts:
                # Slice using word timestamps
                ch_words = [
                    w.word for w in words
                    if w.start >= ch.start_seconds and w.end <= ch.end_seconds
                ]
                ch.transcript = " ".join(ch_words).strip()
            else:
                # Fallback: proportional character slicing from prepared_text
                if duration > 0 and len(prepared_text) > 0:
                    start_char = int((ch.start_seconds / duration) * len(prepared_text))
                    end_char = int((ch.end_seconds / duration) * len(prepared_text))
                    ch.transcript = prepared_text[start_char:end_char].strip()
                else:
                    ch.transcript = ""

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

    @staticmethod
    def _parse_hms_duration(duration: str) -> int:
        """Parse 'HH:MM:SS.mmm' or 'MM:SS' duration string into total seconds."""
        try:
            parts = duration.split(":")
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + int(float(s))
            if len(parts) == 2:
                m, s = parts
                return int(m) * 60 + int(float(s))
            return int(float(parts[0]))
        except (ValueError, AttributeError):
            return 0

    def _render_chapter_guidance(self, prompt: str, total_duration: str) -> str:
        """Render the {{PREFERRED_CHAPTERS_BLOCK}} and {{CHAPTER_GUIDANCE}} placeholders.

        - PREFERRED_CHAPTERS_BLOCK: a short line telling the LLM the user's target.
        - CHAPTER_GUIDANCE: the actual numeric rules the LLM should follow, which
          differ based on whether preferred_chapters is set or not.
        """
        total_seconds = self._parse_hms_duration(total_duration)
        if self.preferred_chapters is not None:
            preferred_block = (
                f"Número de capítulos objetivo (recomendación del usuario): **{self.preferred_chapters}**\n"
                f"Este es un OBJETIVO FLEXIBLE: el LLM puede generar MENOS capítulos si el contenido "
                f"tiene menos temas naturales, pero no debe exceder este número en más de ~20%."
            )
            chapter_guidance = (
                f"- **El usuario pidió ~{self.preferred_chapters} capítulos**. Intenta acercarte a ese número.\n"
                f"- Si el contenido solo tiene {max(1, self.preferred_chapters - 3)} temas reales, genera {max(1, self.preferred_chapters - 3)} capítulos "
                f"(es mejor tener MENOS capítulos bien agrupados que muchos fragmentados).\n"
                f"- Si el contenido tiene más temas de los que el target permite, mantén el target y agrupa "
                f"temas relacionados en capítulos temáticos más amplios (ej: 'Diseño CAD completo' en lugar de "
                f"'diseño de margen', 'diseño de spacer', 'diseño de hombro' por separado).\n"
                f"- Prioriza SIEMPRE la coherencia temática sobre el número exacto."
            )
        else:
            preferred_block = (
                "Número de capítulos objetivo: **no especificado — usar heurística de duración**\n"
                "Aplica las guías por defecto según la duración del video (ver más abajo)."
            )
            minutes = total_seconds / 60
            if minutes < 5:
                chapter_guidance = "- Video de menos de 5 minutos: 1-2 capítulos máximo."
            elif minutes < 15:
                chapter_guidance = "- Video de 5-15 minutos: 2-4 capítulos."
            elif minutes < 30:
                chapter_guidance = "- Video de 15-30 minutos: 3-6 capítulos."
            elif minutes < 60:
                chapter_guidance = "- Video de 30-60 minutos: 6-10 capítulos."
            elif minutes < 120:
                chapter_guidance = "- Video de 1-2 horas: 10-15 capítulos."
            else:
                chapter_guidance = "- Video de más de 2 horas: 15-20 capítulos."
            chapter_guidance += "\n- Regla general: capítulos de 5-10 minutos cada uno para videos largos."

        prompt = prompt.replace("{{PREFERRED_CHAPTERS_BLOCK}}", preferred_block)
        prompt = prompt.replace("{{CHAPTER_GUIDANCE}}", chapter_guidance)
        return prompt