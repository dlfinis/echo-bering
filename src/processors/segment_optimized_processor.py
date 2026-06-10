"""Optimized transcript processor for segment-level timestamp providers like Groq.

This processor uses segment-level timestamps to provide precise timing information
while keeping the LLM prompt clean and focused on content analysis rather than
technical timing details.

The strategy:
1. Send clean text + context to LLM for semantic segmentation
2. Post-process LLM results using actual segment timestamps  
3. Assign precise start/end times based on real audio timing
4. Maintain chapter coherence through macro-level validation
"""

from typing import List, Dict, Any, Optional
import logging

from src.models.chapter import Chapter
from src.processors.transcript_preprocessor import preprocess_transcript
from src.providers.asr.base import TranscriptResult
from src.processors.transcript_processor import TranscriptProcessor, _format_duration

logger = logging.getLogger(__name__)


class SegmentOptimizedProcessor(TranscriptProcessor):
    """Processor optimized for providers with segment-level timestamps (like Groq).

    Uses segment timing data to provide precise chapter boundaries while keeping
    the LLM prompt focused on semantic content analysis.
    """

    def get_prompt_filename(self) -> str:
        """Use the standard segmenter prompt (clean text only)."""
        return "segmenter.md"

    def prepare_transcript_text(self, transcript: TranscriptResult) -> str:
        """Return clean transcript text without technical timing annotations.
        
        The LLM should focus on semantic content, not technical timing details.
        Real timing will be applied during post-processing.
        Preprocessing cleans unicode and removes repetitions.
        """
        return preprocess_transcript(transcript.text)

    def get_total_duration_str(self, transcript: TranscriptResult) -> str:
        """Format total duration from transcript metadata."""
        return _format_duration(transcript.duration_s) if transcript.duration_s > 0 else "00:00:00.000"

    def post_process_chapters(self, chapters: List[Chapter], transcript: TranscriptResult) -> List[Chapter]:
        """Post-process LLM-generated chapters with real segment timestamps.
        
        This is the key optimization: LLM provides semantic boundaries,
        but we use actual audio timing for precise timestamps.
        """
        if not transcript.has_segments():
            logger.warning("No segments available for post-processing, returning chapters as-is")
            return chapters

        # Validate and enhance chapters with real timing
        enhanced_chapters = []
        total_duration = transcript.duration_s
        
        for i, chapter in enumerate(chapters):
            # Estimate chapter boundaries based on text proportion
            chapter_start_ratio = self._estimate_start_ratio(chapter, transcript.text)
            chapter_end_ratio = self._estimate_end_ratio(chapter, transcript.text)
            
            # Convert ratios to actual timestamps using segments
            start_time = self._find_timestamp_by_ratio(chapter_start_ratio, transcript.segments, total_duration)
            end_time = self._find_timestamp_by_ratio(chapter_end_ratio, transcript.segments, total_duration)
            
            # Ensure chronological order and valid boundaries
            if i > 0:
                start_time = max(start_time, enhanced_chapters[-1].end_seconds + 0.1)
            if end_time <= start_time:
                end_time = start_time + 1.0
            if end_time > total_duration:
                end_time = total_duration
            
            # Create enhanced chapter with real timing
            enhanced_chapter = Chapter(
                number=chapter.number,
                title=chapter.title,
                start_time=_format_duration(start_time),
                end_time=_format_duration(end_time),
                start_seconds=start_time,
                end_seconds=end_time,
                confidence=chapter.confidence,
                transcript=chapter.transcript,
                needs_review=chapter.needs_review
            )
            enhanced_chapters.append(enhanced_chapter)
            
            logger.debug(
                f"Enhanced chapter {chapter.number}: {start_time:.2f}s - {end_time:.2f}s "
                f"(confidence: {chapter.confidence:.2f})"
            )
        
        # Validate macro coherence
        self._validate_chapter_coherence(enhanced_chapters, total_duration)
        
        return enhanced_chapters

    def _estimate_start_ratio(self, chapter: Chapter, full_text: str) -> float:
        """Estimate the start ratio of a chapter within the full text."""
        if not chapter.transcript:
            return 0.0
        
        # Find approximate position of chapter text in full transcript
        chapter_start = full_text.find(chapter.transcript[:50])  # First 50 chars
        if chapter_start == -1:
            chapter_start = full_text.find(chapter.transcript[:20])  # Fallback to 20 chars
        
        return max(0.0, chapter_start / len(full_text)) if len(full_text) > 0 else 0.0

    def _estimate_end_ratio(self, chapter: Chapter, full_text: str) -> float:
        """Estimate the end ratio of a chapter within the full text."""
        if not chapter.transcript:
            return 1.0
        
        # Find approximate end position
        chapter_end = full_text.find(chapter.transcript[-50:])  # Last 50 chars
        if chapter_end == -1:
            chapter_end = full_text.find(chapter.transcript[-20:])  # Fallback to 20 chars
        
        if chapter_end == -1:
            return 1.0
        
        return min(1.0, (chapter_end + len(chapter.transcript[-50:])) / len(full_text)) if len(full_text) > 0 else 1.0

    def _find_timestamp_by_ratio(self, ratio: float, segments: List[Dict[str, Any]], total_duration: float) -> float:
        """Find the actual timestamp corresponding to a text ratio using segments."""
        if ratio <= 0.0:
            return 0.0
        if ratio >= 1.0:
            return total_duration
        
        target_position = ratio * total_duration
        
        # Find the segment that contains this timestamp
        for segment in segments:
            segment_start = segment.get("start", 0.0)
            segment_end = segment.get("end", 0.0)
            
            if segment_start <= target_position <= segment_end:
                return target_position
        
        # If not found exactly, find closest segment
        closest_segment = min(segments, key=lambda s: abs(s.get("start", 0.0) - target_position))
        return closest_segment.get("start", target_position)

    def _validate_chapter_coherence(self, chapters: List[Chapter], total_duration: float) -> None:
        """Validate macro-level chapter coherence and fix issues."""
        if len(chapters) == 0:
            return
        
        # Ensure first chapter starts at 0
        if chapters[0].start_seconds > 1.0:
            chapters[0].start_seconds = 0.0
            chapters[0].start_time = _format_duration(0.0)
        
        # Ensure last chapter ends at total duration
        if chapters[-1].end_seconds < total_duration - 1.0:
            chapters[-1].end_seconds = total_duration
            chapters[-1].end_time = _format_duration(total_duration)
        
        # Ensure no gaps or overlaps
        for i in range(1, len(chapters)):
            prev_end = chapters[i-1].end_seconds
            curr_start = chapters[i].start_seconds
            
            if curr_start < prev_end:
                # Overlap - adjust current start
                chapters[i].start_seconds = prev_end + 0.1
                chapters[i].start_time = _format_duration(chapters[i].start_seconds)
            elif curr_start > prev_end + 5.0:
                # Large gap - extend previous chapter
                chapters[i-1].end_seconds = curr_start - 0.1
                chapters[i-1].end_time = _format_duration(chapters[i-1].end_seconds)