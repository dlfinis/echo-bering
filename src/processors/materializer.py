"""Chapter materialization — physical output generation.

ChapterMaterializer creates chapter folders with metadata.json, SRT subtitles,
and video clips. Uses ffmpeg fast cut (stream copy) for video extraction.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Union

from src.models.chapter import Chapter, EnrichedChapter
from src.providers.asr.base import TranscriptResult, WordTimestamp
from src.utils.errors import DependencyError
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Seconds gap between words to start a new SRT entry
_SRT_GAP_THRESHOLD = 2.0


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
) -> List[Tuple[float, float, str]]:
    """Group word timestamps into SRT entries based on time gaps.

    Words within gap_threshold seconds of each other are grouped into
    a single SRT entry.

    Args:
        words: List of word-level timestamps.
        gap_threshold: Max seconds between words to group them.

    Returns:
        List of (start, end, text) tuples for SRT entries.
    """
    if not words:
        return []

    entries: List[Tuple[float, float, str]] = []
    current_words: List[str] = [words[0].word]
    current_start = words[0].start
    current_end = words[0].end

    for word in words[1:]:
        if word.start - current_end > gap_threshold:
            # Gap detected — finalize current entry
            entries.append((current_start, current_end, " ".join(current_words)))
            current_words = [word.word]
            current_start = word.start
            current_end = word.end
        else:
            current_words.append(word.word)
            current_end = word.end

    # Finalize last entry
    entries.append((current_start, current_end, " ".join(current_words)))
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
        slug = base_chapter.title.lower().replace(" ", "-")

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

        slug = base_chapter.title.lower().replace(" ", "-")
        chapter_dir = self.chapters_dir / slug
        chapter_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write SRT subtitles
        srt_content = self.generate_srt(transcript.words)
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
