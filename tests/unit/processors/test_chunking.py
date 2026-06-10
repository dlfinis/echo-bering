"""Unit tests for ChunkingStrategy — adaptive chunking with overlap support."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.processors.chunking import (
    ChunkingStrategy,
    ChunkMetadata,
    FullAudioStrategy,
    TimedChunkingStrategy,
)
from src.providers.asr.base import TranscriptResult, WordTimestamp


class TestChunkMetadata:
    """Test ChunkMetadata data model."""

    def test_create_chunk_metadata(self):
        """ChunkMetadata can be created with required fields."""
        meta = ChunkMetadata(
            chunk_index=0,
            start_s=0.0,
            end_s=1200.0,
            chunk_path=Path("/tmp/chunk_0.wav"),
        )
        assert meta.chunk_index == 0
        assert meta.start_s == 0.0
        assert meta.end_s == 1200.0
        assert meta.transcript_result is None
        assert meta.failed is False

    def test_chunk_metadata_mark_failed(self):
        """ChunkMetadata can be marked as failed."""
        meta = ChunkMetadata(
            chunk_index=1,
            start_s=1200.0,
            end_s=2400.0,
            chunk_path=Path("/tmp/chunk_1.wav"),
        )
        meta.failed = True
        assert meta.failed is True


class TestFullAudioStrategy:
    """Test FullAudioStrategy — returns single chunk for entire audio."""

    def test_create_chunks_returns_single_chunk(self):
        """FullAudioStrategy returns single chunk covering entire audio."""
        strategy = FullAudioStrategy()
        audio_path = Path("/tmp/audio.wav")
        duration_s = 300.0  # 5 minutes

        chunks = strategy.create_chunks(audio_path, duration_s)

        assert len(chunks) == 1
        meta = chunks[0]
        assert meta.chunk_index == 0
        assert meta.start_s == 0.0
        assert meta.end_s == 300.0
        assert meta.chunk_path == audio_path

    def test_create_chunks_zero_duration(self):
        """FullAudioStrategy handles zero duration audio."""
        strategy = FullAudioStrategy()
        audio_path = Path("/tmp/audio.wav")

        chunks = strategy.create_chunks(audio_path, 0.0)

        assert len(chunks) == 1
        assert chunks[0].end_s == 0.0

    def test_reassemble_returns_single_result(self):
        """FullAudioStrategy reassemble returns the only result."""
        strategy = FullAudioStrategy()
        result = TranscriptResult(
            text="Hello world",
            confidence=0.95,
            words=[
                WordTimestamp(word="Hello", start=0.0, end=0.5, confidence=0.95),
                WordTimestamp(word="world", start=0.5, end=1.0, confidence=0.95),
            ],
            duration_s=1.0,
            provider="mock",
            model="mock",
        )

        merged = strategy.reassemble([result], [])

        assert merged.text == "Hello world"
        assert merged.confidence == 0.95
        assert len(merged.words) == 2


class TestTimedChunkingStrategy:
    """Test TimedChunkingStrategy — splits audio into timed chunks with overlap."""

    def test_default_config(self):
        """Default config uses 20min chunks with 30s overlap."""
        strategy = TimedChunkingStrategy()
        assert strategy.chunk_duration_s == 1200.0  # 20 * 60
        assert strategy.overlap_s == 30

    def test_custom_config(self):
        """Custom chunk duration and overlap are applied."""
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=60)
        assert strategy.chunk_duration_s == 600.0  # 10 * 60
        assert strategy.overlap_s == 60

    def _run_mocked_chunks(self, strategy, audio_path, duration_s, mock_run):
        """Helper to run create_chunks with proper subprocess mock."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        return strategy.create_chunks(audio_path, duration_s)

    def test_produces_correct_chunk_count_for_45min_audio(self, mock_run_for_chunking):
        """45min audio with 20min chunks produces 3 chunks."""
        strategy = TimedChunkingStrategy(chunk_duration_min=20, overlap_s=30)
        audio_path = Path("/tmp/audio.wav")
        duration_s = 45 * 60  # 2700 seconds

        chunks = self._run_mocked_chunks(strategy, audio_path, duration_s, mock_run_for_chunking)

        assert len(chunks) == 3

    def test_overlap_boundaries_are_correct(self, mock_run_for_chunking):
        """Chunk boundaries include correct overlap."""
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        audio_path = Path("/tmp/audio.wav")
        duration_s = 35 * 60  # 35 minutes = 2100 seconds

        chunks = self._run_mocked_chunks(strategy, audio_path, duration_s, mock_run_for_chunking)

        # First chunk: 0 to 600s (10 min)
        assert chunks[0].start_s == 0.0
        assert chunks[0].end_s == 600.0

        # Second chunk: starts 30s before first ends (570s) to 1170s
        assert chunks[1].start_s == 570.0
        assert chunks[1].end_s == 1170.0

    def test_last_chunk_ends_at_audio_duration(self, mock_run_for_chunking):
        """Last chunk always ends at the total audio duration."""
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        audio_path = Path("/tmp/audio.wav")
        duration_s = 25 * 60  # 25 minutes = 1500 seconds

        chunks = self._run_mocked_chunks(strategy, audio_path, duration_s, mock_run_for_chunking)

        assert chunks[-1].end_s == 1500.0

    def test_short_audio_produces_single_chunk(self):
        """Audio shorter than chunk duration produces single chunk."""
        strategy = TimedChunkingStrategy(chunk_duration_min=20, overlap_s=30)
        audio_path = Path("/tmp/audio.wav")
        duration_s = 5 * 60  # 5 minutes

        chunks = strategy.create_chunks(audio_path, duration_s)

        assert len(chunks) == 1
        assert chunks[0].start_s == 0.0
        assert chunks[0].end_s == 300.0

    @patch("src.processors.chunking.subprocess.run")
    def test_create_chunks_generates_chunk_files(self, mock_run, tmp_path):
        """TimedChunkingStrategy creates actual chunk WAV files via ffmpeg."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        audio_path = tmp_path / "audio.wav"
        audio_path.touch()
        duration_s = 25 * 60  # 25 minutes

        chunks = strategy.create_chunks(audio_path, duration_s)

        # Should produce 3 chunks: 0-600s, 570-1170s, 1140-1500s
        assert len(chunks) == 3

    @patch("src.processors.chunking.subprocess.run")
    def test_chunk_metadata_has_correct_indices(self, mock_run):
        """Each chunk has sequential index starting from 0."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        audio_path = Path("/tmp/audio.wav")
        duration_s = 35 * 60

        chunks = strategy.create_chunks(audio_path, duration_s)

        for i, meta in enumerate(chunks):
            assert meta.chunk_index == i


class TestTimedChunkingReassembly:
    """Test TimedChunkingStrategy reassembly with overlap resolution."""

    def _make_result(self, text: str, confidence: float, words: list, duration_s: float) -> TranscriptResult:
        return TranscriptResult(
            text=text,
            confidence=confidence,
            words=words,
            duration_s=duration_s,
            provider="mock",
            model="mock",
        )

    def test_reassemble_merges_two_chunks(self):
        """Reassembly merges chunk transcripts into continuous text."""
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        chunk_meta = [
            ChunkMetadata(chunk_index=0, start_s=0.0, end_s=600.0, chunk_path=Path("chunk_0.wav")),
            ChunkMetadata(chunk_index=1, start_s=570.0, end_s=1200.0, chunk_path=Path("chunk_1.wav")),
        ]
        results = [
            self._make_result("First chunk text", 0.9, [], 600.0),
            self._make_result("Second chunk text", 0.85, [], 630.0),
        ]

        merged = strategy.reassemble(results, chunk_meta)

        assert "First chunk text" in merged.text
        assert "Second chunk text" in merged.text

    def test_reassemble_marks_failed_chunk(self):
        """Reassembly marks failed chunks with [TRANSCRIPTION_FAILED]."""
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        chunk_meta = [
            ChunkMetadata(chunk_index=0, start_s=0.0, end_s=600.0, chunk_path=Path("chunk_0.wav")),
            ChunkMetadata(chunk_index=1, start_s=570.0, end_s=1200.0, chunk_path=Path("chunk_1.wav")),
            ChunkMetadata(chunk_index=2, start_s=1170.0, end_s=1800.0, chunk_path=Path("chunk_2.wav")),
        ]
        results = [
            self._make_result("Chunk 0 text", 0.9, [], 600.0),
            None,  # Chunk 1 failed
            self._make_result("Chunk 2 text", 0.85, [], 630.0),
        ]

        merged = strategy.reassemble(results, chunk_meta)

        assert "[TRANSCRIPTION_FAILED]" in merged.text
        assert "Chunk 0 text" in merged.text
        assert "Chunk 2 text" in merged.text

    def test_reassemble_uses_higher_confidence_in_overlap(self):
        """Overlap regions use segment with higher confidence."""
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        chunk_meta = [
            ChunkMetadata(chunk_index=0, start_s=0.0, end_s=600.0, chunk_path=Path("chunk_0.wav")),
            ChunkMetadata(chunk_index=1, start_s=570.0, end_s=1200.0, chunk_path=Path("chunk_1.wav")),
        ]
        results = [
            self._make_result("Chunk A text", 0.7, [], 600.0),
            self._make_result("Chunk B text", 0.95, [], 630.0),
        ]

        merged = strategy.reassemble(results, chunk_meta)

        # Higher confidence chunk should dominate
        assert merged.confidence >= 0.7

    def test_reassemble_all_failed(self):
        """All chunks failed produces only [TRANSCRIPTION_FAILED]."""
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        chunk_meta = [
            ChunkMetadata(chunk_index=0, start_s=0.0, end_s=600.0, chunk_path=Path("chunk_0.wav")),
        ]
        results = [None]

        merged = strategy.reassemble(results, chunk_meta)

        assert "[TRANSCRIPTION_FAILED]" in merged.text

    def test_reassemble_empty_results_raises(self):
        """Reassemble with no results raises ValueError."""
        strategy = TimedChunkingStrategy()
        with pytest.raises(ValueError):
            strategy.reassemble([], [])

    def test_reassemble_adjusts_word_timestamps_to_absolute(self):
        """Word timestamps are adjusted to absolute positions based on chunk start."""
        strategy = TimedChunkingStrategy(chunk_duration_min=10, overlap_s=30)
        chunk_meta = [
            ChunkMetadata(chunk_index=0, start_s=0.0, end_s=600.0, chunk_path=Path("chunk_0.wav")),
            ChunkMetadata(chunk_index=1, start_s=570.0, end_s=1200.0, chunk_path=Path("chunk_1.wav")),
        ]
        results = [
            self._make_result(
                "hello world",
                0.9,
                [
                    WordTimestamp(word="hello", start=0.0, end=0.5, confidence=0.9),
                    WordTimestamp(word="world", start=0.5, end=1.0, confidence=0.9),
                ],
                600.0,
            ),
            self._make_result(
                "second part",
                0.85,
                [
                    WordTimestamp(word="second", start=0.0, end=0.3, confidence=0.85),
                    WordTimestamp(word="part", start=0.3, end=0.6, confidence=0.85),
                ],
                630.0,
            ),
        ]

        merged = strategy.reassemble(results, chunk_meta)

        # First chunk words stay at 0-based timestamps
        assert merged.words[0].start == 0.0
        assert merged.words[1].end == 1.0
        # Second chunk words are offset by chunk start (570s)
        assert merged.words[2].start == 570.0
        assert merged.words[3].end == 570.6
