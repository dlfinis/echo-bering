"""Shared pytest fixtures for Echo-Bering tests.

Provides mock providers, test audio, golden data, and temporary directories.
"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.providers.asr.base import TranscriptResult, WordTimestamp

# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_asr_provider():
    """Mock ASR provider returning a minimal TranscriptResult."""
    provider = MagicMock()
    provider.transcribe = AsyncMock(
        return_value=TranscriptResult(
            text="Sample transcription text.",
            confidence=0.95,
            words=[
                WordTimestamp(word="Sample", start=0.0, end=0.5, confidence=0.95),
                WordTimestamp(word="transcription", start=0.5, end=1.0, confidence=0.95),
                WordTimestamp(word="text.", start=1.0, end=1.5, confidence=0.93),
            ],
            duration_s=1.5,
            provider="mock",
            model="mock-model",
        )
    )
    provider.supports_file = AsyncMock(return_value=True)
    return provider


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider returning a chapter dict."""
    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value={
            "chapters": [
                {
                    "number": 1,
                    "title": "Introduction",
                    "start_time": "00:00:00.000",
                    "end_time": "00:00:30.000",
                    "start_seconds": 0.0,
                    "end_seconds": 30.0,
                    "confidence": 0.92,
                    "transcript": "Sample transcript for the introduction chapter.",
                }
            ]
        }
    )
    return provider


# ---------------------------------------------------------------------------
# Test audio
# ---------------------------------------------------------------------------


@pytest.fixture
def test_audio_path(tmp_path):
    """Create a minimal WAV file in tmp_path for testing."""
    audio_path = tmp_path / "test.wav"
    # Minimal valid WAV header: 1 channel, 16000 Hz, 16-bit PCM
    # RIFF header + fmt chunk + data chunk
    wav_data = (
        b"RIFF"           # ChunkID
        b"\x24\x00\x00\x00"  # ChunkSize (36 + data)
        b"WAVE"           # Format
        b"fmt "           # Subchunk1ID
        b"\x10\x00\x00\x00"  # Subchunk1Size (16)
        b"\x01\x00"       # AudioFormat (PCM)
        b"\x01\x00"       # NumChannels (1)
        b"\x80\x3e\x00\x00"  # SampleRate (16000)
        b"\x00\xfa\x00\x00"  # ByteRate (32000)
        b"\x02\x00"       # BlockAlign (2)
        b"\x10\x00"       # BitsPerSample (16)
        b"data"           # Subchunk2ID
        b"\x00\x00\x00\x00"  # Subchunk2Size (0 bytes of audio data)
    )
    audio_path.write_bytes(wav_data)
    return audio_path


# ---------------------------------------------------------------------------
# Golden data
# ---------------------------------------------------------------------------


@pytest.fixture
def golden_transcript():
    """Golden file for transcript validation."""
    return {
        "text": "Sample transcription text.",
        "confidence": 0.95,
        "words": [
            {"word": "Sample", "start": 0.0, "end": 0.5, "confidence": 0.95},
            {"word": "transcription", "start": 0.5, "end": 1.0, "confidence": 0.95},
            {"word": "text.", "start": 1.0, "end": 1.5, "confidence": 0.93},
        ],
        "duration_s": 1.5,
        "provider": "mock",
        "model": "mock-model",
    }


# ---------------------------------------------------------------------------
# Mock ffmpeg
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ffmpeg():
    """Mock subprocess.run for ffmpeg calls."""
    mock = MagicMock()
    mock.return_value.returncode = 0
    mock.return_value.stderr = ""
    return mock


# ---------------------------------------------------------------------------
# Temporary output directory
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_output_dir(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
