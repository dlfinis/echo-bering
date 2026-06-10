"""ASR provider domain models and abstract interface.

WordTimestamp and TranscriptResult are shared data structures used across
the pipeline. ASRProvider is the abstract interface for provider implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

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
    words: List[WordTimestamp] = Field(default_factory=list)
    segments: List[Dict[str, Any]] = Field(default_factory=list)  # Segment-level timestamps from providers like Groq
    duration_s: float = Field(default=0.0)
    provider: str
    model: str

    def has_word_timestamps(self) -> bool:
        """Check if this transcript contains word-level timing data."""
        return len(self.words) > 0

    def has_segments(self) -> bool:
        """Check if this transcript contains segment-level timing data."""
        return len(self.segments) > 0

    def get_word_at_time(self, seconds: float) -> Optional[WordTimestamp]:
        """Find the word that overlaps the given timestamp.

        Args:
            seconds: Time offset in seconds from the start of the audio.

        Returns:
            The WordTimestamp covering that moment, or None if no match.
        """
        if not self.words:
            return None
        for w in self.words:
            if w.start <= seconds <= w.end:
                return w
        return None

    def get_duration_per_word(self) -> float:
        """Calculate average duration per word.

        Returns 0.0 if no words or no duration data.
        """
        if not self.words or self.duration_s <= 0:
            return 0.0
        return round(self.duration_s / len(self.words), 4)

    def get_segment_at_time(self, seconds: float) -> Optional[Dict[str, Any]]:
        """Find the segment that contains the given timestamp.

        Args:
            seconds: Time offset in seconds from the start of the audio.

        Returns:
            The segment dict containing that moment, or None if no match.
        """
        if not self.segments:
            return None
        for segment in self.segments:
            start = segment.get("start", 0.0)
            end = segment.get("end", 0.0)
            if start <= seconds <= end:
                return segment
        return None


@dataclass(frozen=True)
class ProviderCapabilities:
    """Metadata about what features an ASR provider supports.

    Attributes:
        has_word_timestamps: Provider returns word-level start/end times.
        has_speaker_diarization: Provider can identify different speakers.
        has_utterances: Provider returns utterance-level segmentation.
        max_duration_s: Maximum audio duration the provider accepts (0 = unlimited).
    """

    has_word_timestamps: bool = False
    has_speaker_diarization: bool = False
    has_utterances: bool = False
    max_duration_s: float = 0.0

    def supports_feature(self, feature: str) -> bool:
        """Check if this provider supports a named feature.

        Args:
            feature: Feature name (e.g. "word_timestamps", "speaker_diarization").

        Returns:
            True if the feature is available.
        """
        feature_map = {
            "word_timestamps": self.has_word_timestamps,
            "speaker_diarization": self.has_speaker_diarization,
            "utterances": self.has_utterances,
        }
        return feature_map.get(feature, False)


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

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return the capability profile of this provider."""
        ...
