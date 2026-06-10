"""Unit tests for AudioExtractor — ffmpeg wrapper for audio extraction."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.processors.audio_extractor import AudioExtractor
from src.utils.errors import DependencyError


class TestAudioExtractorInit:
    """Test AudioExtractor initialization."""

    def test_init_with_default_output_dir(self, tmp_path):
        extractor = AudioExtractor(output_dir=tmp_path)
        assert extractor.output_dir == tmp_path
        expected_audio_dir = tmp_path / ".checkpoint" / "audio"
        assert extractor.audio_dir == expected_audio_dir

    def test_init_creates_audio_directory(self, tmp_path):
        output_dir = tmp_path / "output"
        extractor = AudioExtractor(output_dir=output_dir)
        assert extractor.audio_dir.exists()


class TestAudioExtractorExtract:
    """Test AudioExtractor.extract() method."""

    @patch("src.processors.audio_extractor.shutil.which")
    @patch("src.processors.audio_extractor.subprocess.run")
    def test_successful_extraction_calls_ffmpeg_with_correct_args(
        self, mock_run, mock_which, tmp_path
    ):
        """Successful extraction calls ffmpeg with correct args."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video_path = tmp_path / "test.mp4"
        video_path.touch()

        extractor = AudioExtractor(output_dir=tmp_path)
        result = extractor.extract(str(video_path))

        assert result == extractor.audio_dir / "audio.wav"
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "ffmpeg" in cmd
        assert "-i" in cmd
        assert str(video_path) in cmd
        assert "-ar" in cmd
        assert "16000" in cmd
        assert "-ac" in cmd
        assert "1" in cmd
        assert str(result) in cmd

    @patch("src.processors.audio_extractor.shutil.which")
    def test_ffmpeg_not_found_raises_dependency_error(self, mock_which, tmp_path):
        """ffmpeg not found raises DependencyError with instructions."""
        mock_which.return_value = None

        video_path = tmp_path / "test.mp4"
        video_path.touch()

        extractor = AudioExtractor(output_dir=tmp_path)

        with pytest.raises(DependencyError) as exc_info:
            extractor.extract(str(video_path))

        assert exc_info.value.dependency == "ffmpeg"
        assert "install" in exc_info.value.instructions.lower()

    @patch("src.processors.audio_extractor.shutil.which")
    @patch("src.processors.audio_extractor.subprocess.run")
    def test_ffmpeg_error_propagates_stderr_and_return_code(
        self, mock_run, mock_which, tmp_path
    ):
        """ffmpeg error propagates stderr + return code."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Error: Unsupported codec",
        )

        video_path = tmp_path / "test.mp4"
        video_path.touch()

        extractor = AudioExtractor(output_dir=tmp_path)

        with pytest.raises(RuntimeError) as exc_info:
            extractor.extract(str(video_path))

        assert "Unsupported codec" in str(exc_info.value)
        assert "return code 1" in str(exc_info.value)

    @patch("src.processors.audio_extractor.shutil.which")
    @patch("src.processors.audio_extractor.subprocess.run")
    def test_output_path_is_16khz_mono_wav(self, mock_run, mock_which, tmp_path):
        """Output path points to 16kHz mono WAV file."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video_path = tmp_path / "test.mov"
        video_path.touch()

        extractor = AudioExtractor(output_dir=tmp_path)
        result = extractor.extract(str(video_path))

        assert result.suffix == ".wav"
        assert result.name == "audio.wav"

    @patch("src.processors.audio_extractor.shutil.which")
    @patch("src.processors.audio_extractor.subprocess.run")
    def test_supports_mp4_format(self, mock_run, mock_which, tmp_path):
        """Supports .mp4 container."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video_path = tmp_path / "test.mp4"
        video_path.touch()

        extractor = AudioExtractor(output_dir=tmp_path)
        result = extractor.extract(str(video_path))
        assert result.exists() is False  # File not actually created in mock
        assert result.suffix == ".wav"

    @patch("src.processors.audio_extractor.shutil.which")
    @patch("src.processors.audio_extractor.subprocess.run")
    def test_supports_mov_format(self, mock_run, mock_which, tmp_path):
        """Supports .mov container."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video_path = tmp_path / "test.mov"
        video_path.touch()

        extractor = AudioExtractor(output_dir=tmp_path)
        result = extractor.extract(str(video_path))
        assert result.suffix == ".wav"

    @patch("src.processors.audio_extractor.shutil.which")
    @patch("src.processors.audio_extractor.subprocess.run")
    def test_supports_avi_format(self, mock_run, mock_which, tmp_path):
        """Supports .avi container."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video_path = tmp_path / "test.avi"
        video_path.touch()

        extractor = AudioExtractor(output_dir=tmp_path)
        result = extractor.extract(str(video_path))
        assert result.suffix == ".wav"

    @patch("src.processors.audio_extractor.shutil.which")
    @patch("src.processors.audio_extractor.subprocess.run")
    def test_supports_mkv_format(self, mock_run, mock_which, tmp_path):
        """Supports .mkv container."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video_path = tmp_path / "test.mkv"
        video_path.touch()

        extractor = AudioExtractor(output_dir=tmp_path)
        result = extractor.extract(str(video_path))
        assert result.suffix == ".wav"
