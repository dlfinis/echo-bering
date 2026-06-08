"""Adaptive transcript processors for capability-aware segmentation.

The processing strategy is selected based on provider capabilities:
- BasicTranscriptProcessor: for providers without word-level timestamps
- AdvancedTranscriptProcessor: for providers with word-level timestamps

Both produce the same Chapter output format.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.models.chapter import Chapter
from src.processors.transcript_preprocessor import preprocess_transcript
from src.providers.asr.base import ProviderCapabilities, TranscriptResult


class TranscriptProcessor(ABC):
    """Abstract base for transcript processing strategies."""

    @abstractmethod
    def get_prompt_filename(self) -> str:
        """Return the prompt template filename for this processor."""
        ...

    @abstractmethod
    def prepare_transcript_text(self, transcript: TranscriptResult) -> str:
        """Prepare the transcript text for LLM segmentation.

        Args:
            transcript: The full transcript result from the ASR provider.

        Returns:
            Text to pass to the LLM for chapter segmentation.
        """
        ...

    @abstractmethod
    def get_total_duration_str(self, transcript: TranscriptResult) -> str:
        """Format the total duration as HH:MM:SS string.

        Args:
            transcript: The transcript result with duration data.

        Returns:
            Duration string in HH:MM:SS format.
        """
        ...


def _format_duration(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted duration string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


class BasicTranscriptProcessor(TranscriptProcessor):
    """Processor for providers without word-level timestamps.

    Uses the full transcript text and total duration.
    The LLM must estimate chapter boundaries from text structure.
    
    DEPRECATED: Use CleanTranscriptProcessor instead.
    """

    def get_prompt_filename(self) -> str:
        return "segmenter-basic.md"

    def prepare_transcript_text(self, transcript: TranscriptResult) -> str:
        """Return the plain transcript text without timestamp annotations.
        
        Applies preprocessing to clean unicode characters and remove
        repetitions before sending to the LLM.
        """
        return preprocess_transcript(transcript.text)

    def get_total_duration_str(self, transcript: TranscriptResult) -> str:
        """Format the total duration from the transcript metadata."""
        return _format_duration(transcript.duration_s) if transcript.duration_s > 0 else "00:00:00.000"


class CleanTranscriptProcessor(TranscriptProcessor):
    """Advanced processor that cleans transcripts before processing.
    
    Applies full preprocessing pipeline including:
    - Unicode normalization (¡, ¿, í, é, etc.)
    - ASR marker removal (aplausos, risas, música, etc.)
    - Filler word removal (um, eh, este, etc.)
    - Repetition reduction
    - Punctuation normalization
    
    This processor should be used for all production pipelines.
    
    NOTE: This processor assumes the transcript has already been preprocessed
    by the transcriber. It only applies light normalization for safety.
    """

    def get_prompt_filename(self) -> str:
        return "segmenter-basic.md"

    def prepare_transcript_text(self, transcript: TranscriptResult) -> str:
        """Return transcript text (already preprocessed by transcriber).
        
        Since the transcriber already applies preprocessing, this processor
        only returns the text as-is to avoid double processing.
        """
        return transcript.text

    def get_total_duration_str(self, transcript: TranscriptResult) -> str:
        """Format the total duration from the transcript metadata."""
        return _format_duration(transcript.duration_s) if transcript.duration_s > 0 else "00:00:00.000"


class AdvancedTranscriptProcessor(TranscriptProcessor):
    """Processor for providers with word-level timestamps.

    Can include timestamp annotations in the transcript text
    for more precise chapter boundary detection.
    """

    def get_prompt_filename(self) -> str:
        return "segmenter.md"

    def prepare_transcript_text(self, transcript: TranscriptResult) -> str:
        """Return the transcript text with preprocessing applied.
        
        The advanced prompt is designed to work with plain text.
        Word timestamps are available for post-processing if needed.
        Preprocessing cleans unicode and removes repetitions.
        """
        return preprocess_transcript(transcript.text)

    def get_total_duration_str(self, transcript: TranscriptResult) -> str:
        """Format the total duration from the transcript metadata."""
        return _format_duration(transcript.duration_s) if transcript.duration_s > 0 else "00:00:00.000"


def select_processor(capabilities: ProviderCapabilities, transcript: Optional[TranscriptResult] = None) -> TranscriptProcessor:
    """Select the appropriate processor based on provider capabilities and transcript data.
    
    Args:
        capabilities: The provider's capability profile.
        transcript: Optional transcript result to check for segment data.
        
    Returns:
        A TranscriptProcessor instance matching the available capabilities and data.
    """
    # Check for segment-level timestamps (Groq with verbose_json)
    if transcript and transcript.has_segments():
        from src.processors.segment_optimized_processor import SegmentOptimizedProcessor
        return SegmentOptimizedProcessor()
    
    # Check for word-level timestamps (AssemblyAI, mlx-whisper with word_timestamps=True)
    if capabilities.has_word_timestamps:
        return AdvancedTranscriptProcessor()
    
    # Default: Use clean processor with full preprocessing
    return CleanTranscriptProcessor()
