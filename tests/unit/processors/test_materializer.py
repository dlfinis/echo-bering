"""Unit tests for ChapterMaterializer — physical output generation."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.models.chapter import Chapter
from src.processors.materializer import (
    ChapterMaterializer,
    _format_srt_timestamp,
    _group_words_into_entries,
)
from src.providers.asr.base import TranscriptResult, WordTimestamp


class TestSrtTimestampFormatting:
    """Test SRT timestamp formatting utility."""

    def test_zero_seconds(self):
        """0.0 seconds formats as 00:00:00,000."""
        assert _format_srt_timestamp(0.0) == "00:00:00,000"

    def test_one_second(self):
        """1.0 seconds formats correctly."""
        assert _format_srt_timestamp(1.0) == "00:00:01,000"

    def test_fractional_milliseconds(self):
        """Fractional seconds include milliseconds."""
        assert _format_srt_timestamp(1.5) == "00:00:01,500"

    def test_minutes_and_seconds(self):
        """Values over 60 seconds produce minutes."""
        assert _format_srt_timestamp(65.25) == "00:01:05,250"

    def test_hours(self):
        """Values over 3600 seconds produce hours."""
        assert _format_srt_timestamp(3661.123) == "01:01:01,123"

    def test_large_timestamp(self):
        """Large timestamps format correctly."""
        assert _format_srt_timestamp(7325.456) == "02:02:05,456"


class TestGroupWordsIntoEntries:
    """Test word grouping into SRT entries."""

    def test_single_word(self):
        """Single word produces one entry."""
        words = [WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.95)]
        entries = _group_words_into_entries(words)
        assert len(entries) == 1
        assert entries[0] == (0.0, 0.5, "Hello")

    def test_two_words(self):
        """Two consecutive words produce one entry."""
        words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.95),
            WordTimestamp(word="world", start=0.6, end=1.0, confidence=0.93),
        ]
        entries = _group_words_into_entries(words)
        assert len(entries) == 1
        assert entries[0] == (0.0, 1.0, "Hello world")

    def test_words_with_gap_produce_separate_entries(self):
        """Words separated by >2s gap produce separate entries."""
        words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.95),
            WordTimestamp(word="later", start=5.0, end=5.5, confidence=0.90),
        ]
        entries = _group_words_into_entries(words)
        assert len(entries) == 2
        assert entries[0] == (0.0, 0.5, "Hello")
        assert entries[1] == (5.0, 5.5, "later")

    def test_many_words_grouped(self):
        """Multiple consecutive words grouped into one entry."""
        words = [
            WordTimestamp(word="This", start=0.0, end=0.3, confidence=0.95),
            WordTimestamp(word="is", start=0.4, end=0.6, confidence=0.95),
            WordTimestamp(word="a", start=0.7, end=0.8, confidence=0.95),
            WordTimestamp(word="test", start=0.9, end=1.2, confidence=0.95),
        ]
        entries = _group_words_into_entries(words)
        assert len(entries) == 1
        assert entries[0] == (0.0, 1.2, "This is a test")

    def test_empty_word_list(self):
        """Empty list produces no entries."""
        assert _group_words_into_entries([]) == []


class TestChapterMaterializerSrtGeneration:
    """Test SRT file generation from word timestamps."""

    def test_generate_srt_from_words(self, tmp_path):
        """SRT file generated from word timestamps."""
        materializer = ChapterMaterializer(output_dir=tmp_path)
        words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.95),
            WordTimestamp(word="world", start=0.6, end=1.0, confidence=0.93),
        ]
        srt_path = tmp_path / "test-chapter" / "test-chapter.srt"
        srt_path.parent.mkdir(parents=True)

        srt_content = materializer.generate_srt(words)

        expected = (
            "1\n"
            "00:00:00,000 --> 00:00:01,000\n"
            "Hello world\n"
        )
        assert srt_content == expected

    def test_generate_srt_multiple_entries(self, tmp_path):
        """SRT file with multiple entries from gapped timestamps."""
        materializer = ChapterMaterializer(output_dir=tmp_path)
        words = [
            WordTimestamp(word="First", start=0.0, end=0.5, confidence=0.95),
            WordTimestamp(word="Second", start=10.0, end=10.5, confidence=0.90),
            WordTimestamp(word="Third", start=20.0, end=20.5, confidence=0.88),
        ]
        srt_content = materializer.generate_srt(words)

        lines = srt_content.strip().split("\n")
        # Each entry has 3 lines: number, timestamps, text, plus blank separators
        assert len(lines) == 11  # 3*3 + 2 blank separators
        assert "1" in lines[0]
        assert "2" in lines[4]
        assert "3" in lines[8]

    def test_generate_srt_empty_words(self, tmp_path):
        """Empty word list produces empty SRT content."""
        materializer = ChapterMaterializer(output_dir=tmp_path)
        assert materializer.generate_srt([]) == ""


class TestChapterMaterializerMetadata:
    """Test metadata.json generation."""

    def _make_chapter(self):
        return Chapter(
            number=1,
            title="Introduction",
            start_time="00:00:00.000",
            end_time="00:02:30.000",
            start_seconds=0.0,
            end_seconds=150.0,
            confidence=0.85,
            transcript="Welcome to this video.",
            needs_review=False,
        )

    def test_write_metadata_json(self, tmp_path):
        """Metadata JSON written with correct structure."""
        chapter = self._make_chapter()
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_metadata(
            chapter=chapter,
            transcription_confidence=0.92,
            output_path=tmp_path / "metadata.json",
        )

        with open(tmp_path / "metadata.json", "r") as f:
            data = json.load(f)

        assert data["title"] == "Introduction"
        assert data["slug"] == "introduction"
        assert data["start_time"] == "00:00:00.000"
        assert data["end_time"] == "00:02:30.000"
        assert data["start_seconds"] == 0.0
        assert data["end_seconds"] == 150.0
        assert data["summary"] == "Welcome to this video."
        assert data["key_topics"] == []
        assert data["confidence"] == 0.85
        assert data["transcription_confidence"] == 0.92

    def test_write_metadata_with_key_topics(self, tmp_path):
        """Metadata includes key topics when provided."""
        chapter = self._make_chapter()
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_metadata(
            chapter=chapter,
            transcription_confidence=0.92,
            output_path=tmp_path / "metadata.json",
            key_topics=["Python", "Basics"],
        )

        with open(tmp_path / "metadata.json", "r") as f:
            data = json.load(f)

        assert data["key_topics"] == ["Python", "Basics"]

    def test_metadata_creates_parent_directory(self, tmp_path):
        """write_metadata creates parent directories if missing."""
        chapter = self._make_chapter()
        materializer = ChapterMaterializer(output_dir=tmp_path)
        output_path = tmp_path / "deep" / "nested" / "metadata.json"

        materializer.write_metadata(
            chapter=chapter,
            transcription_confidence=0.90,
            output_path=output_path,
        )

        assert output_path.exists()


class TestChapterMaterializerVideoCut:
    """Test video clip extraction via ffmpeg."""

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_cut_video_clip_fast_mode(self, mock_run, mock_which, tmp_path):
        """Video cut uses ffmpeg stream copy (fast mode)."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        materializer = ChapterMaterializer(output_dir=tmp_path)
        source_video = Path("/videos/source.mp4")
        output_clip = tmp_path / "intro.mp4"

        result = materializer.cut_video_clip(
            source_video=source_video,
            start_seconds=0.0,
            end_seconds=150.0,
            output_path=output_clip,
        )

        # Verify ffmpeg called with stream copy (fast mode)
        call_args = mock_run.call_args[0][0]
        assert "ffmpeg" in call_args[0]
        assert "-ss" in call_args
        assert "0.0" in call_args
        assert "-to" in call_args
        assert "150.0" in call_args
        assert "-c" in call_args
        assert "copy" in call_args
        assert result == output_clip

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_cut_video_clip_ffmpeg_not_installed(self, mock_run, mock_which, tmp_path):
        """Raises DependencyError when ffmpeg not found."""
        mock_which.return_value = None

        materializer = ChapterMaterializer(output_dir=tmp_path)

        from src.utils.errors import DependencyError
        with pytest.raises(DependencyError):
            materializer.cut_video_clip(
                source_video=Path("/videos/source.mp4"),
                start_seconds=0.0,
                end_seconds=150.0,
                output_path=tmp_path / "clip.mp4",
            )

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_cut_video_clip_ffmpeg_failure(self, mock_run, mock_which, tmp_path):
        """Raises RuntimeError when ffmpeg fails."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=1, stderr="Invalid argument")

        materializer = ChapterMaterializer(output_dir=tmp_path)

        with pytest.raises(RuntimeError):
            materializer.cut_video_clip(
                source_video=Path("/videos/source.mp4"),
                start_seconds=0.0,
                end_seconds=150.0,
                output_path=tmp_path / "clip.mp4",
            )


class TestChapterMaterializerFullMaterialize:
    """Test the full materialize method."""

    def _make_chapter(self):
        return Chapter(
            number=1,
            title="Introduction",
            start_time="00:00:00.000",
            end_time="00:02:30.000",
            start_seconds=0.0,
            end_seconds=150.0,
            confidence=0.85,
            transcript="Welcome to this video.",
            needs_review=False,
        )

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_materialize_creates_all_files(self, mock_run, mock_which, tmp_path):
        """materialize creates chapter folder with all required files."""
        mock_which.return_value = "/usr/bin/ffmpeg"

        def create_clip(*args, **kwargs):
            output_path = args[-1] if isinstance(args[-1], str) else args[0][-1]
            Path(output_path).touch()
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = create_clip

        chapter = self._make_chapter()
        words = [
            WordTimestamp(word="Welcome", start=0.0, end=0.5, confidence=0.95),
            WordTimestamp(word="to", start=0.6, end=0.8, confidence=0.93),
            WordTimestamp(word="this", start=0.9, end=1.1, confidence=0.94),
            WordTimestamp(word="video.", start=1.2, end=1.5, confidence=0.92),
        ]
        transcript = TranscriptResult(
            text="Welcome to this video.",
            confidence=0.92,
            words=words,
            duration_s=150.0,
            provider="mock",
            model="mock-model",
        )

        materializer = ChapterMaterializer(output_dir=tmp_path)
        source_video = Path("/videos/source.mp4")
        chapter_dir = materializer.materialize(
            chapter=chapter,
            transcript=transcript,
            source_video=source_video,
        )

        # Verify chapter folder structure
        assert chapter_dir.exists()
        assert (chapter_dir / "metadata.json").exists()
        assert (chapter_dir / "introduction.srt").exists()
        assert (chapter_dir / "introduction.mp4").exists()

    def test_materialize_without_video_cut(self, tmp_path):
        """materialize works with source_video=None (no clip generation)."""
        chapter = self._make_chapter()
        words = [
            WordTimestamp(word="Welcome", start=0.0, end=0.5, confidence=0.95),
        ]
        transcript = TranscriptResult(
            text="Welcome",
            confidence=0.95,
            words=words,
            duration_s=150.0,
            provider="mock",
            model="mock-model",
        )

        materializer = ChapterMaterializer(output_dir=tmp_path)
        chapter_dir = materializer.materialize(
            chapter=chapter,
            transcript=transcript,
            source_video=None,
        )

        assert chapter_dir.exists()
        assert (chapter_dir / "metadata.json").exists()
        assert (chapter_dir / "introduction.srt").exists()
        # No mp4 when source_video is None
        assert not (chapter_dir / "introduction.mp4").exists()

    def test_materialize_with_enriched_chapter(self, tmp_path):
        """materialize works with EnrichedChapter for key_topics."""
        from src.models.chapter import EnrichedChapter

        chapter = self._make_chapter()
        enriched = EnrichedChapter(
            chapter=chapter,
            description="Introduction to the topic",
            context="First chapter",
            summary_bullets=["Point 1", "Point 2"],
            terms_used=[],
            key_concepts=["Concept A", "Concept B"],
            entities_detected={},
            highlights=[],
            pedagogy={},
            confidence={"segmentation_score": 0.85, "needs_review": False},
        )
        words = [WordTimestamp(word="Welcome", start=0.0, end=0.5, confidence=0.95)]
        transcript = TranscriptResult(
            text="Welcome",
            confidence=0.92,
            words=words,
            duration_s=150.0,
            provider="mock",
            model="mock-model",
        )

        materializer = ChapterMaterializer(output_dir=tmp_path)
        chapter_dir = materializer.materialize(
            chapter=enriched,
            transcript=transcript,
            source_video=None,
        )

        with open(chapter_dir / "metadata.json", "r") as f:
            data = json.load(f)

        # key_topics should come from key_concepts
        assert "Concept A" in data["key_topics"]
        assert "Concept B" in data["key_topics"]


class TestChapterMaterializerIndex:
    """Test the chapters/index.md generation."""

    def _make_chapter(self, *, number, title, start_seconds, end_seconds, transcript=""):
        return Chapter(
            number=number,
            title=title,
            start_time="00:00:00.000",
            end_time="00:00:00.000",
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            confidence=0.85,
            transcript=transcript,
            needs_review=False,
        )

    def test_write_index_creates_file(self, tmp_path):
        """index.md is created at chapters_dir/index.md."""
        chapters = [self._make_chapter(number=1, title="First", start_seconds=0.0, end_seconds=60.0)]
        materializer = ChapterMaterializer(output_dir=tmp_path)

        result = materializer.write_index(chapters)

        expected = materializer.chapters_dir / "index.md"
        assert result == expected
        assert expected.exists()
        assert expected.is_file()

    def test_write_index_sorts_by_start_seconds(self, tmp_path):
        """Chapters appear in narrative order (start_seconds ascending), not input order."""
        chapters = [
            self._make_chapter(number=3, title="Third", start_seconds=300.0, end_seconds=400.0),
            self._make_chapter(number=1, title="First", start_seconds=0.0, end_seconds=100.0),
            self._make_chapter(number=2, title="Second", start_seconds=150.0, end_seconds=250.0),
        ]
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_index(chapters)
        content = (materializer.chapters_dir / "index.md").read_text(encoding="utf-8")

        # Titles should appear in the file in start_seconds order, not input order
        first_pos = content.find("## 01 — First")
        second_pos = content.find("## 02 — Second")
        third_pos = content.find("## 03 — Third")
        assert first_pos != -1
        assert second_pos != -1
        assert third_pos != -1
        assert first_pos < second_pos < third_pos

    def test_write_index_zero_padded_numbers(self, tmp_path):
        """Chapter headings are zero-padded (01, 02, …)."""
        chapters = [
            self._make_chapter(number=1, title="A", start_seconds=0.0, end_seconds=30.0),
            self._make_chapter(number=2, title="B", start_seconds=30.0, end_seconds=60.0),
            self._make_chapter(number=3, title="C", start_seconds=60.0, end_seconds=90.0),
        ]
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_index(chapters)
        content = (materializer.chapters_dir / "index.md").read_text(encoding="utf-8")

        assert "## 01 — A" in content
        assert "## 02 — B" in content
        assert "## 03 — C" in content

    def test_write_index_handles_enriched_chapter(self, tmp_path):
        """EnrichedChapter renders summary text and key topics line."""
        from src.models.chapter import EnrichedChapter

        base = self._make_chapter(
            number=1, title="Intro", start_seconds=0.0, end_seconds=120.0,
            transcript="base transcript fallback",
        )
        enriched = EnrichedChapter(
            chapter=base,
            description="This chapter introduces the topic thoroughly.",
            context="Setting the stage",
            summary_bullets=["Point A", "Point B"],
            terms_used=[],
            key_concepts=["Topic A", "Topic B"],
            entities_detected={},
            highlights=[],
            pedagogy={},
            confidence={"segmentation_score": 0.9, "needs_review": False},
        )
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_index([enriched])
        content = (materializer.chapters_dir / "index.md").read_text(encoding="utf-8")

        assert "## 01 — Intro" in content
        assert "This chapter introduces the topic thoroughly." in content
        assert "**Key topics**: Topic A, Topic B" in content

    def test_write_index_handles_plain_chapter(self, tmp_path):
        """Plain Chapter works with no key topics line."""
        chapter = self._make_chapter(
            number=1, title="Plain", start_seconds=0.0, end_seconds=60.0,
            transcript="Welcome to the first chapter of this video.",
        )
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_index([chapter])
        content = (materializer.chapters_dir / "index.md").read_text(encoding="utf-8")

        assert "## 01 — Plain" in content
        # No Key topics line for plain Chapter
        assert "**Key topics**" not in content
        # Slug is computed from the title
        assert "**Slug**: `plain`" in content
        assert "**Folder**: `plain/`" in content

    def test_write_index_omits_key_topics_when_empty(self, tmp_path):
        """No **Key topics** line when the list is empty."""
        from src.models.chapter import EnrichedChapter

        base = self._make_chapter(number=1, title="X", start_seconds=0.0, end_seconds=30.0)
        enriched = EnrichedChapter(
            chapter=base,
            description="desc",
            context="ctx",
            summary_bullets=[],
            terms_used=[],
            key_concepts=[],  # empty
            entities_detected={},
            highlights=[],
            pedagogy={},
            confidence={"segmentation_score": 0.9, "needs_review": False},
        )
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_index([enriched])
        content = (materializer.chapters_dir / "index.md").read_text(encoding="utf-8")

        assert "**Key topics**" not in content

    def test_write_index_includes_duration_and_folder(self, tmp_path):
        """Each chapter has **Duration** and **Folder** lines."""
        chapters = [
            self._make_chapter(number=1, title="Hello World", start_seconds=0.0, end_seconds=90.0),
        ]
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_index(chapters)
        content = (materializer.chapters_dir / "index.md").read_text(encoding="utf-8")

        assert "**Duration**:" in content
        assert "1m 30s" in content
        assert "**Folder**: `hello-world/`" in content

    def test_write_index_source_duration_uses_max_end_seconds(self, tmp_path):
        """Source duration header uses the max end_seconds across all chapters."""
        chapters = [
            self._make_chapter(number=1, title="A", start_seconds=0.0, end_seconds=120.0),
            self._make_chapter(number=2, title="B", start_seconds=120.0, end_seconds=300.0),  # max
            self._make_chapter(number=3, title="C", start_seconds=300.0, end_seconds=240.0),  # earlier
        ]
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_index(chapters)
        content = (materializer.chapters_dir / "index.md").read_text(encoding="utf-8")

        # 300s = 5 minutes -> 0:05:00
        assert "Source duration: 0:05:00" in content
        assert "Total: 3 chapters" in content

    def test_write_index_separator_between_chapters(self, tmp_path):
        """A --- separator appears between chapter sections."""
        chapters = [
            self._make_chapter(number=1, title="A", start_seconds=0.0, end_seconds=30.0),
            self._make_chapter(number=2, title="B", start_seconds=30.0, end_seconds=60.0),
            self._make_chapter(number=3, title="C", start_seconds=60.0, end_seconds=90.0),
        ]
        materializer = ChapterMaterializer(output_dir=tmp_path)

        materializer.write_index(chapters)
        content = (materializer.chapters_dir / "index.md").read_text(encoding="utf-8")

        # Two separators between three chapters
        assert content.count("\n---\n") == 2
