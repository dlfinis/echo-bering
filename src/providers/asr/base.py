"""ASR provider domain models and abstract interface.

WordTimestamp and TranscriptResult are shared data structures used across
the pipeline. ASRProvider is the abstract interface for provider implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel, Field


class WordTimestamp(BaseModel):
    """Word-level timestamp with confidence score."""

    word: str
    start: float
    end: float
    confidence: float = Field(default=1.0, ge=0, le=1)


class TranscriptResult(BaseModel):
    """Structured transcription result from an ASR provider."""

    text: str
    confidence: float = Field(default=1.0, ge=0, le=1)
    words: List[WordTimestamp]
    duration_s: float
    provider: str
    model: str


class ASRProvider(ABC):
    """Abstract interface for ASR providers."""

    @abstractmethod
    async def transcribe(self, audio_path: str) -> TranscriptResult:
        """Transcribe audio file and return structured result."""
        ...

    @abstractmethod
    async def supports_file(self, audio_path: str) -> bool:
        """Check if provider can process file (size/duration limits)."""
        ...
