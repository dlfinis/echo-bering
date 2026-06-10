"""Tests for adaptive transcript processors."""

import pytest

from src.providers.asr.base import (
    ProviderCapabilities,
    TranscriptResult,
    WordTimestamp,
)
from src.processors.transcript_processor import (
    BasicTranscriptProcessor,
    AdvancedTranscriptProcessor,
    TranscriptProcessor,
    select_processor,
    _format_duration,
)


class TestFormatDuration:
    """Test duration formatting utility."""

    def test_zero_seconds(self):
        """0 seconds formats as 00:00:00.000."""
        assert _format_duration(0.0) == "00:00:00.000"

    def test_one_minute(self):
        """60 seconds formats as 00:01:00.000."""
        assert _format_duration(60.0) == "00:01:00.000"

    def test_one_hour(self):
        """3600 seconds formats as 01:00:00.000."""
        assert _format_duration(3600.0) == "01:00:00.000"

    def test_with_milliseconds(self):
        """Fractional seconds include milliseconds."""
        result = _format_duration(123.456)
        assert result == "00:02:03.456"

    def test_complex_duration(self):
        """Complex durations format correctly."""
        # 1h 23m 45.678s
        total = 3600 + 23 * 60 + 45.678
        assert _format_duration(total) == "01:23:45.678"


class TestBasicTranscriptProcessor:
    """Test BasicTranscriptProcessor for providers without word timestamps."""

    @pytest.fixture
    def processor(self):
        return BasicTranscriptProcessor()

    def test_prompt_filename(self, processor):
        """Returns the basic prompt filename."""
        assert processor.get_prompt_filename() == "segmenter-basic.md"

    def test_prepare_transcript_returns_plain_text(self, processor):
        """Returns only the text field, no timestamp annotations."""
        transcript = TranscriptResult(
            text="Hello world this is a test",
            confidence=0.9,
            words=[],
            duration_s=10.0,
            provider="test",
            model="test",
        )
        result = processor.prepare_transcript_text(transcript)
        assert result == "Hello world this is a test"

    def test_duration_with_positive_value(self, processor):
        """Formats positive duration correctly."""
        transcript = TranscriptResult(
            text="Hello",
            confidence=1.0,
            provider="test",
            model="test",
            duration_s=125.5,
        )
        assert processor.get_total_duration_str(transcript) == "00:02:05.500"

    def test_duration_with_zero_value(self, processor):
        """Returns default for zero duration."""
        transcript = TranscriptResult(
            text="Hello",
            confidence=1.0,
            provider="test",
            model="test",
            duration_s=0.0,
        )
        assert processor.get_total_duration_str(transcript) == "00:00:00.000"


class TestAdvancedTranscriptProcessor:
    """Test AdvancedTranscriptProcessor for providers with word timestamps."""

    @pytest.fixture
    def processor(self):
        return AdvancedTranscriptProcessor()

    def test_prompt_filename(self, processor):
        """Returns the advanced prompt filename."""
        assert processor.get_prompt_filename() == "segmenter.md"

    def test_prepare_transcript_returns_plain_text(self, processor):
        """Returns the text field (advanced prompt handles plain text)."""
        words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
        ]
        transcript = TranscriptResult(
            text="Hello world",
            confidence=0.95,
            words=words,
            duration_s=1.0,
            provider="test",
            model="test",
        )
        result = processor.prepare_transcript_text(transcript)
        assert result == "Hello world"

    def test_duration_with_positive_value(self, processor):
        """Formats positive duration correctly."""
        transcript = TranscriptResult(
            text="Hello",
            confidence=1.0,
            provider="test",
            model="test",
            duration_s=3661.123,
        )
        assert processor.get_total_duration_str(transcript) == "01:01:01.123"

    def test_duration_with_zero_value(self, processor):
        """Returns default for zero duration."""
        transcript = TranscriptResult(
            text="Hello",
            confidence=1.0,
            provider="test",
            model="test",
            duration_s=0.0,
        )
        assert processor.get_total_duration_str(transcript) == "00:00:00.000"


class TestSelectProcessor:
    """Test processor selection based on capabilities."""

    def test_selects_basic_when_no_timestamps(self):
        """Basic processor selected when word timestamps unavailable."""
        caps = ProviderCapabilities(has_word_timestamps=False)
        processor = select_processor(caps)
        assert isinstance(processor, BasicTranscriptProcessor)

    def test_selects_advanced_when_timestamps_available(self):
        """Advanced processor selected when word timestamps available."""
        caps = ProviderCapabilities(has_word_timestamps=True)
        processor = select_processor(caps)
        assert isinstance(processor, AdvancedTranscriptProcessor)

    def test_selects_basic_for_groq_capabilities(self):
        """Groq capabilities yield basic processor."""
        from src.providers.asr.groq_asr import GROQ_CAPABILITIES
        processor = select_processor(GROQ_CAPABILITIES)
        assert isinstance(processor, BasicTranscriptProcessor)

    def test_selects_advanced_for_assemblyai_capabilities(self):
        """AssemblyAI capabilities yield advanced processor."""
        from src.providers.asr.assemblyai_asr import ASSEMBLYAI_CAPABILITIES
        processor = select_processor(ASSEMBLYAI_CAPABILITIES)
        assert isinstance(processor, AdvancedTranscriptProcessor)

    def test_selects_basic_for_openai_capabilities(self):
        """OpenAI capabilities yield basic processor."""
        from src.providers.asr.openai_asr import OPENAI_CAPABILITIES
        processor = select_processor(OPENAI_CAPABILITIES)
        assert isinstance(processor, BasicTranscriptProcessor)

    def test_processor_is_abstract_base(self):
        """TranscriptProcessor is an abstract base class."""
        from abc import ABC
        assert issubclass(TranscriptProcessor, ABC)


class TestProcessorInterface:
    """Test that processors conform to the interface."""

    def test_basic_processor_has_all_methods(self):
        """BasicProcessor implements all abstract methods."""
        processor = BasicTranscriptProcessor()
        assert callable(getattr(processor, "get_prompt_filename", None))
        assert callable(getattr(processor, "prepare_transcript_text", None))
        assert callable(getattr(processor, "get_total_duration_str", None))

    def test_advanced_processor_has_all_methods(self):
        """AdvancedProcessor implements all abstract methods."""
        processor = AdvancedTranscriptProcessor()
        assert callable(getattr(processor, "get_prompt_filename", None))
        assert callable(getattr(processor, "prepare_transcript_text", None))
        assert callable(getattr(processor, "get_total_duration_str", None))
