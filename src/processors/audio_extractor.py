"""Audio extraction via ffmpeg subprocess wrapper.

Extracts mono 16kHz WAV audio from video files (mp4, mov, avi, mkv).
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from src.utils.errors import DependencyError
from src.utils.logger import get_logger

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


class AudioExtractor:
    """Extract audio from video files using ffmpeg.

    Outputs a mono 16kHz WAV file suitable for ASR transcription.
    """

    def __init__(self, output_dir: Path):
        """Initialize AudioExtractor.

        Args:
            output_dir: Base output directory. Audio goes to
                output_dir/.checkpoint/audio/audio.wav.
        """
        self.output_dir = output_dir
        self.audio_dir = output_dir / ".checkpoint" / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def extract(self, video_path: str, output_path: Optional[Path] = None) -> Path:
        """Extract audio from a video file.

        Args:
            video_path: Path to the input video file.
            output_path: Optional custom output path. Defaults to
                audio_dir/audio.wav.

        Returns:
            Path to the extracted WAV file.

        Raises:
            DependencyError: If ffmpeg is not found on PATH.
            RuntimeError: If ffmpeg fails during extraction.
        """
        self._check_ffmpeg()

        video = Path(video_path)
        if output_path is None:
            output_path = self.audio_dir / "audio.wav"

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-ar", "16000",
            "-ac", "1",
            "-sample_fmt", "s16",
            str(output_path),
        ]

        logger.info("Extracting audio: %s -> %s", video_path, output_path)
        logger.debug("ffmpeg command: %s", " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = (
                f"ffmpeg failed with return code {result.returncode}: "
                f"{result.stderr.strip()}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info("Audio extraction complete: %s", output_path)
        return output_path

    def _check_ffmpeg(self) -> None:
        """Verify ffmpeg is available on PATH.

        Raises:
            DependencyError: If ffmpeg is not found.
        """
        if shutil.which("ffmpeg") is None:
            raise DependencyError(
                dependency="ffmpeg",
                instructions=(
                    "ffmpeg is required for audio extraction. "
                    "Install via: brew install ffmpeg (macOS), "
                    "apt install ffmpeg (Ubuntu/Debian), or "
                    "choco install ffmpeg (Windows)."
                ),
            )
