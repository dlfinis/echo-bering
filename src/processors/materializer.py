"""Chapter materialization — physical output generation.

ChapterMaterializer creates chapter folders with metadata.json, SRT subtitles,
and video clips. Uses ffmpeg fast cut (stream copy) for video extraction.
"""

import json
from pathlib import Path
import shutil
import subprocess
from typing import List

from src.models.transcription import WordTimestamp
from src.providers.asr.base import TranscriptResult
from src.orchestrators.utils import slugify
from typing import List, Optional, Tuple, Union

from src.models.chapter import Chapter, EnrichedChapter
from src.providers.asr.base import TranscriptResult
from src.utils.errors import DependencyError
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Seconds gap between words to start a new SRT entry
_SRT_GAP_THRESHOLD = 0.5  # seconds between words to create new SRT entry


def _format_srt_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted SRT timestamp string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _group_words_into_entries(
    words: List[WordTimestamp],
    gap_threshold: float = _SRT_GAP_THRESHOLD,
    max_words_per_entry: int = 25,
    sentence_endings: set = None,
) -> List[Tuple[float, float, str]]:
    """Group word timestamps into SRT entries based on time gaps and sentence structure.
    
    Creates entries that respect natural sentence boundaries while avoiding
    overly long subtitles. Uses punctuation and word count heuristics.
    
    Args:
        words: List of word-level timestamps.
        gap_threshold: Max seconds between words to consider them part of same entry.
        max_words_per_entry: Maximum words per SRT entry to avoid overcrowding.
        sentence_endings: Punctuation marks that indicate sentence endings.
        
    Returns:
        List of (start, end, text) tuples for SRT entries.
    """
    if not words:
        return []
    
    if sentence_endings is None:
        sentence_endings = {".", "!", "?", "...", ":", ";"}
    
    entries: List[Tuple[float, float, str]] = []
    current_words: List[str] = []
    current_start = words[0].start
    current_end = words[0].end
    
    for i, word in enumerate(words):
        # Add current word
        current_words.append(word.word)
        current_end = word.end
        
        # Check if we should split here
        should_split = False
        
        # Split on sentence endings
        if any(ending in word.word for ending in sentence_endings):
            should_split = True
            
        # Split if we've reached max words
        if len(current_words) >= max_words_per_entry:
            should_split = True
            
        # Split on large time gaps
        if i < len(words) - 1:  # Not the last word
            next_word = words[i + 1]
            if next_word.start - word.end > gap_threshold:
                should_split = True
                
        # Create new entry if needed
        if should_split and current_words:
            # Clean up the text
            text = " ".join(current_words)
            # Remove extra spaces around punctuation
            text = text.replace(" .", ".").replace(" ,", ",").replace(" ?", "?").replace(" !", "!")
            text = text.strip()
            
            if text:  # Only add non-empty entries
                entries.append((current_start, current_end, text))
            
            # Reset for next entry
            if i < len(words) - 1:
                current_words = []
                current_start = words[i + 1].start
                current_end = words[i + 1].end
    
    # Handle remaining words
    if current_words:
        text = " ".join(current_words)
        text = text.replace(" .", ".").replace(" ,", ",").replace(" ?", "?").replace(" !", "!")
        text = text.strip()
        if text:
            entries.append((current_start, current_end, text))
    
    return entries


class ChapterMaterializer:
    """Generate physical chapter output files.

    Creates chapter folders with metadata.json, .srt subtitles, and
    video clips via ffmpeg fast cut.
    """

    def __init__(self, output_dir: Path):
        """Initialize ChapterMaterializer.

        Args:
            output_dir: Base output directory. Chapters go to output_dir/chapters/.
        """
        self.output_dir = output_dir
        self.chapters_dir = output_dir / "chapters"
        self.chapters_dir.mkdir(parents=True, exist_ok=True)

    def generate_srt(self, words: List[WordTimestamp]) -> str:
        """Generate SRT content from word-level timestamps.

        Args:
            words: Word-level timestamps from ASR transcription.

        Returns:
            SRT file content as string.
        """
        if not words:
            return ""

        entries = _group_words_into_entries(words)
        lines = []
        for i, (start, end, text) in enumerate(entries, 1):
            lines.append(str(i))
            lines.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
            lines.append(text)
            lines.append("")  # blank line separator

        return "\n".join(lines)

    def _generate_srt_from_text(
        self,
        text: str,
        start_seconds: float,
        end_seconds: float,
    ) -> str:
        """Generate SRT content from plain text without word timestamps.

        Splits text into chunks and distributes them proportionally across
        the chapter's time range.

        Args:
            text: Chapter transcript text.
            start_seconds: Chapter start time in seconds.
            end_seconds: Chapter end time in seconds.

        Returns:
            SRT file content as string.
        """
        if not text:
            return ""

        # Split text into sentences (rough heuristic)
        sentences = []
        current = []
        for char in text:
            current.append(char)
            if char in '.!?' and len(current) > 10:
                sentences.append(''.join(current).strip())
                current = []
        if current:
            sentences.append(''.join(current).strip())

        # Filter out empty sentences
        sentences = [s for s in sentences if s]

        if not sentences:
            return ""

        # Distribute sentences across the time range
        duration = end_seconds - start_seconds
        time_per_sentence = duration / len(sentences)

        lines = []
        for i, sentence in enumerate(sentences, 1):
            sent_start = start_seconds + (i - 1) * time_per_sentence
            sent_end = start_seconds + i * time_per_sentence
            lines.append(str(i))
            lines.append(f"{_format_srt_timestamp(sent_start)} --> {_format_srt_timestamp(sent_end)}")
            lines.append(sentence)
            lines.append("")  # blank line separator

        return "\n".join(lines)

    def write_metadata(
        self,
        chapter: Union[Chapter, EnrichedChapter],
        transcription_confidence: float,
        output_path: Path,
        key_topics: Optional[List[str]] = None,
    ) -> Path:
        """Write metadata.json for a chapter.

        Args:
            chapter: Chapter or EnrichedChapter to serialize.
            transcription_confidence: Confidence from ASR transcription.
            output_path: Where to write the metadata.json file.
            key_topics: Optional list of key topics (defaults to empty).

        Returns:
            Path to the written file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Extract data from Chapter or EnrichedChapter
        if isinstance(chapter, EnrichedChapter):
            base_chapter = chapter.chapter
            topics = key_topics or [c.get("term", "") for c in chapter.key_concepts] if isinstance(chapter.key_concepts, list) and chapter.key_concepts and isinstance(chapter.key_concepts[0], dict) else chapter.key_concepts or []
            summary = chapter.description or base_chapter.transcript
        else:
            base_chapter = chapter
            topics = key_topics or []
            summary = base_chapter.transcript

        # Generate slug from title
        slug = slugify(base_chapter.title)

        metadata = {
            "title": base_chapter.title,
            "slug": slug,
            "start_time": base_chapter.start_time,
            "end_time": base_chapter.end_time,
            "start_seconds": base_chapter.start_seconds,
            "end_seconds": base_chapter.end_seconds,
            "summary": summary,
            "key_topics": topics,
            "confidence": base_chapter.confidence,
            "transcription_confidence": transcription_confidence,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info("Metadata written: %s", output_path)
        return output_path

    def cut_video_clip(
        self,
        source_video: Path,
        start_seconds: float,
        end_seconds: float,
        output_path: Path,
    ) -> Path:
        """Extract a video clip using ffmpeg fast cut (stream copy).

        Args:
            source_video: Path to the source video file.
            start_seconds: Clip start time in seconds.
            end_seconds: Clip end time in seconds.
            output_path: Where to write the clip.

        Returns:
            Path to the created clip file.

        Raises:
            DependencyError: If ffmpeg is not found.
            RuntimeError: If ffmpeg fails.
        """
        if shutil.which("ffmpeg") is None:
            raise DependencyError(
                dependency="ffmpeg",
                instructions=(
                    "ffmpeg is required for video cutting. "
                    "Install via: brew install ffmpeg (macOS), "
                    "apt install ffmpeg (Ubuntu/Debian), or "
                    "choco install ffmpeg (Windows)."
                ),
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(source_video),
            "-ss", str(start_seconds),
            "-to", str(end_seconds),
            "-c", "copy",
            str(output_path),
        ]

        logger.info("Cutting video clip: %s (%.1f–%.1f)", output_path.name, start_seconds, end_seconds)
        logger.debug("ffmpeg command: %s", " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = f"ffmpeg cut failed (code {result.returncode}): {result.stderr.strip()}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info("Video clip created: %s", output_path)
        return output_path

    def materialize(
        self,
        chapter: Union[Chapter, EnrichedChapter],
        transcript: TranscriptResult,
        source_video: Optional[Path] = None,
    ) -> Path:
        """Materialize a complete chapter folder.

        Creates the chapter directory with metadata.json, .srt, and .mp4 clip.

        Args:
            chapter: Chapter or EnrichedChapter to materialize.
            transcript: Full transcript with word-level timestamps.
            source_video: Optional source video for clip extraction.

        Returns:
            Path to the created chapter directory.
        """
        # Use the base chapter for common fields
        if isinstance(chapter, EnrichedChapter):
            base_chapter = chapter.chapter
            topics = chapter.key_concepts if isinstance(chapter.key_concepts, list) and chapter.key_concepts and isinstance(chapter.key_concepts[0], str) else []
        else:
            base_chapter = chapter
            topics = []

        slug = slugify(base_chapter.title)
        chapter_dir = self.chapters_dir / slug
        chapter_dir.mkdir(parents=True, exist_ok=True)

        # Filter words to only those within the chapter's time range
        chapter_words = []
        for word in transcript.words:
            # Include words that overlap with the chapter time range
            if word.end >= base_chapter.start_seconds and word.start <= base_chapter.end_seconds:
                chapter_words.append(word)
        
        # 1. Write SRT subtitles
        # If we have word-level timestamps, generate precise SRT
        # Otherwise, generate a simple SRT with the chapter transcript
        if chapter_words:
            logger.info("Generating SRT from %d word-level timestamps", len(chapter_words))
            srt_content = self.generate_srt(chapter_words)
        else:
            # Fallback: Generate SRT from chapter transcript text
            logger.info("No word-level timestamps, generating SRT from chapter transcript text")
            logger.info("Chapter transcript length: %d characters", len(base_chapter.transcript))
            srt_content = self._generate_srt_from_text(
                base_chapter.transcript,
                base_chapter.start_seconds,
                base_chapter.end_seconds
            )
            logger.info("Generated SRT content length: %d characters", len(srt_content))
        
        srt_path = chapter_dir / f"{slug}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        logger.info("SRT written: %s", srt_path)

        # 2. Write metadata.json
        self.write_metadata(
            chapter=chapter,
            transcription_confidence=transcript.confidence,
            output_path=chapter_dir / "metadata.json",
            key_topics=topics,
        )

        # 3. Cut video clip (optional)
        if source_video is not None:
            clip_path = chapter_dir / f"{slug}.mp4"
            try:
                self.cut_video_clip(
                    source_video=source_video,
                    start_seconds=base_chapter.start_seconds,
                    end_seconds=base_chapter.end_seconds,
                    output_path=clip_path,
                )
            except DependencyError:
                logger.warning("ffmpeg not available — skipping video clip for chapter '%s'", slug)

        logger.info("Chapter materialized: %s", chapter_dir)
        return chapter_dir
