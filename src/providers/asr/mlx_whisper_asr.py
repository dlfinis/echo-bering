"""MLX Whisper ASR provider implementation.

Uses Apple MLX framework for local, GPU-accelerated Whisper transcription.
Supports word-level timestamps and speaker diarization when available.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.models.transcription import WordTimestamp
from src.providers.asr.base import (
    ASRProvider,
    ProviderCapabilities,
    TranscriptResult,
)
from src.utils.errors import PermanentProviderError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MLXWhisperASR(ASRProvider):
    """MLX Whisper ASR provider for local transcription."""

    def __init__(self, model: str = "base"):
        """Initialize MLX Whisper provider.
        
        Args:
            model: Whisper model size (tiny, base, small, medium, large, large-v2, large-v3).
                   Default is 'base' for balance of speed and accuracy.
        """
        super().__init__()
        self._model = model
        
        # Lazy import to avoid dependency issues
        try:
            import mlx_whisper
            self._mlx_whisper = mlx_whisper
        except ImportError as e:
            raise PermanentProviderError(
                f"MLX Whisper not available: {e}. Install with: pip install mlx-whisper"
            ) from e

    @property
    def name(self) -> str:
        return "mlx-whisper"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            has_word_timestamps=True,
            has_speaker_diarization=False,  # Not supported by mlx-whisper
            has_utterances=False,
            max_duration_s=3600,  # 60 minutes max (limited by memory)
        )

    async def transcribe(self, audio_path: Path) -> TranscriptResult:
        """Transcribe audio using MLX Whisper.
        
        Args:
            audio_path: Path to audio file.
            
        Returns:
            TranscriptResult with word-level timestamps if available.
            
        Raises:
            PermanentProviderError: If audio file is invalid or model fails.
        """
        path = Path(audio_path)
        if not path.exists():
            raise PermanentProviderError(f"Audio file not found: {audio_path}")

        try:
            # Transcribe with word-level timestamps
            # Note: mlx-whisper uses its own model mapping, so we map our model names
            # to the appropriate MLX models
            model_map = {
                "tiny": "mlx-community/whisper-tiny",
                "base": "mlx-community/whisper-base",
                "small": "mlx-community/whisper-small",
                "medium": "mlx-community/whisper-medium",
                "large": "mlx-community/whisper-large",
                "large-v2": "mlx-community/whisper-large-v2",
                "large-v3": "mlx-community/whisper-large-v3",
                "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
                "large-v3-mlx": "mlx-community/whisper-large-v3-turbo",
            }
            
            # Use default model if ours isn't in the map, or if there are auth issues
            model_repo = model_map.get(self._model, None)
            
            if model_repo:
                result = self._mlx_whisper.transcribe(
                    str(path),
                    path_or_hf_repo=model_repo,
                    word_timestamps=True,
                    verbose=False,
                )
            else:
                # Fall back to default model (whisper-tiny)
                result = self._mlx_whisper.transcribe(
                    str(path),
                    word_timestamps=True,
                    verbose=False,
                )
            
            # Extract transcript text
            transcript_text = result.get("text", "").strip()
            if not transcript_text:
                raise PermanentProviderError("Empty transcription result")
                
            # Calculate confidence (mlx-whisper doesn't provide per-word confidence)
            # Use a reasonable default based on model size
            model_confidence_map = {
                "tiny": 0.6,
                "base": 0.7,
                "small": 0.8,
                "medium": 0.85,
                "large": 0.9,
                "large-v2": 0.92,
                "large-v3": 0.94,
                "large-v3-turbo": 0.93,
                "large-v3-mlx": 0.93,
            }
            confidence = model_confidence_map.get(self._model, 0.7)
            
            # Extract word-level timestamps from segments
            words = []
            if "segments" in result:
                for segment in result["segments"]:
                    if "words" in segment:
                        for word_data in segment["words"]:
                            words.append(
                                WordTimestamp(
                                    word=word_data["word"].strip(),
                                    start=word_data["start"],
                                    end=word_data["end"],
                                    # mlx-whisper doesn't provide confidence per word
                                    confidence=confidence,
                                )
                            )
            
            # Calculate duration from last word or use audio duration
            duration_s = 0.0
            if words:
                duration_s = words[-1].end
            else:
                # Fallback: estimate from audio file
                try:
                    import subprocess
                    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
                    output = subprocess.check_output(cmd, text=True).strip()
                    duration_s = float(output)
                except (subprocess.SubprocessError, ValueError):
                    duration_s = len(transcript_text) / 15.0  # Rough estimate: 15 chars/sec
                    
            return TranscriptResult(
                text=transcript_text,
                confidence=confidence,
                words=words,
                segments=[],  # mlx-whisper doesn't provide segments like Groq
                duration_s=duration_s,
                provider=self.name,
                model=self._model,
            )
            
        except Exception as e:
            logger.error("MLX Whisper transcription failed: %s", e)
            raise PermanentProviderError(f"MLX Whisper transcription failed: {e}") from e

    async def supports_file(self, audio_path: str) -> bool:
        """Check if provider can process file (size/duration limits).
        
        MLX Whisper is limited by available GPU memory, but we'll assume
        it can handle reasonable file sizes (<60 minutes).
        """
        try:
            import subprocess
            cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", audio_path]
            output = subprocess.check_output(cmd, text=True).strip()
            duration_s = float(output)
            return duration_s <= (60 * 60)  # 60 minutes max
        except (subprocess.SubprocessError, ValueError):
            # If we can't determine duration, assume it's supported
            return True