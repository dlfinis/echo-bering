"""Tests for capability-aware segmenter integration."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.chapter import Chapter
from src.providers.asr.base import (
    ProviderCapabilities,
    TranscriptResult,
    WordTimestamp,
)
from src.processors.segmenter import ChapterSegmenter, PromptManager
from src.processors.transcript_processor import (
    BasicTranscriptProcessor,
    AdvancedTranscriptProcessor,
)
from src.providers.llm.base import LLMResponse


class TestCapabilityAwareSegmenter:
    """Test ChapterSegmenter with capability-aware processor selection."""

    def _make_llm_response(self, chapters_data):
        """Create a mock LLMResponse with chapter data."""
        return LLMResponse(
            text=json.dumps(chapters_data),
            usage={"prompt_tokens": 100, "completion_tokens": 200},
            provider="mock",
            model="mock-model",
        )

    def _make_segmenter(self, mock_llm, tmp_path, **kwargs):
        """Create a segmenter with mock LLM and temp prompt dir."""
        # Create both prompts in the temp dir with all variables
        (tmp_path / "segmenter.md").write_text(
            "Advanced: {{VIDEO_TITLE}} / Duration: {{VIDEO_TOTAL_DURATION}} / {{FULL_TRANSCRIPT}}"
        )
        (tmp_path / "segmenter-basic.md").write_text(
            "Basic: {{VIDEO_TITLE}} / Duration: {{VIDEO_TOTAL_DURATION}} / {{FULL_TRANSCRIPT}}"
        )

        return ChapterSegmenter(
            llm_provider=mock_llm,
            prompt_manager=PromptManager(prompt_dir=tmp_path),
            **kwargs,
        )

    @pytest.mark.asyncio
    async def test_segmenter_selects_basic_processor_for_basic_capabilities(self, tmp_path):
        """Basic capabilities select the basic processor and prompt."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Test Chapter",
                    "start_time": "00:00:00.000",
                    "end_time": "00:01:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "confidence": 0.8,
                    "transcript": "Test content",
                }
            ])
        )

        caps = ProviderCapabilities(has_word_timestamps=False)
        segmenter = self._make_segmenter(mock_llm, tmp_path, capabilities=caps)

        assert isinstance(segmenter._processor, BasicTranscriptProcessor)
        assert segmenter.prompt_filename == "segmenter-basic.md"

    @pytest.mark.asyncio
    async def test_segmenter_selects_advanced_processor_for_rich_capabilities(self, tmp_path):
        """Rich capabilities select the advanced processor and prompt."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Test Chapter",
                    "start_time": "00:00:00.000",
                    "end_time": "00:01:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "confidence": 0.9,
                    "transcript": "Test content",
                }
            ])
        )

        caps = ProviderCapabilities(has_word_timestamps=True)
        segmenter = self._make_segmenter(mock_llm, tmp_path, capabilities=caps)

        assert isinstance(segmenter._processor, AdvancedTranscriptProcessor)
        assert segmenter.prompt_filename == "segmenter.md"

    @pytest.mark.asyncio
    async def test_segmenter_detects_from_transcript_result(self, tmp_path):
        """Segmenter detects capabilities from TranscriptResult."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Test",
                    "start_time": "00:00:00.000",
                    "end_time": "00:01:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "confidence": 0.85,
                    "transcript": "Test",
                }
            ])
        )

        # Transcript with words → advanced processor
        transcript = TranscriptResult(
            text="Hello world",
            confidence=0.9,
            words=[WordTimestamp(word="Hello", start=0.0, end=0.5)],
            duration_s=10.0,
            provider="test",
            model="test",
        )
        segmenter = self._make_segmenter(mock_llm, tmp_path, transcript=transcript)

        assert isinstance(segmenter._processor, AdvancedTranscriptProcessor)

    @pytest.mark.asyncio
    async def test_segmenter_detects_basic_from_empty_words(self, tmp_path):
        """TranscriptResult with empty words → basic processor."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Test",
                    "start_time": "00:00:00.000",
                    "end_time": "00:01:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "confidence": 0.75,
                    "transcript": "Test",
                }
            ])
        )

        transcript = TranscriptResult(
            text="Hello world",
            confidence=0.9,
            words=[],  # No words → basic
            duration_s=10.0,
            provider="test",
            model="test",
        )
        segmenter = self._make_segmenter(mock_llm, tmp_path, transcript=transcript)

        assert isinstance(segmenter._processor, BasicTranscriptProcessor)

    @pytest.mark.asyncio
    async def test_segmenter_uses_processor_duration(self, tmp_path):
        """Segmenter uses processor's duration formatting when transcript_result provided."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Test",
                    "start_time": "00:00:00.000",
                    "end_time": "00:05:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 300.0,
                    "confidence": 0.8,
                    "transcript": "Test",
                }
            ])
        )

        transcript = TranscriptResult(
            text="Hello world",
            confidence=0.9,
            words=[],
            duration_s=300.0,  # 5 minutes
            provider="test",
            model="test",
        )
        segmenter = self._make_segmenter(mock_llm, tmp_path, transcript=transcript)

        chapters = await segmenter.segment(
            transcript="Hello world",
            video_title="Test Video",
            video_topic="Testing",
            video_total_duration="00:00:00",  # This should be overridden
            transcript_result=transcript,
        )

        # Verify the LLM was called with the proper duration
        call_args = mock_llm.generate.call_args
        prompt = call_args[1]["prompt"] if "prompt" in call_args[1] else call_args[0][0]
        assert "00:05:00" in prompt  # Duration from transcript_result

    @pytest.mark.asyncio
    async def test_segmenter_fallback_to_prompt_filename(self, tmp_path):
        """When no capabilities or transcript, uses prompt_filename to select processor."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Test",
                    "start_time": "00:00:00.000",
                    "end_time": "00:01:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "confidence": 0.8,
                    "transcript": "Test",
                }
            ])
        )

        # Default segmenter with advanced prompt filename
        segmenter = self._make_segmenter(mock_llm, tmp_path)
        assert isinstance(segmenter._processor, AdvancedTranscriptProcessor)
        assert segmenter.prompt_filename == "segmenter.md"

    @pytest.mark.asyncio
    async def test_segmenter_fallback_to_basic_prompt_filename(self, tmp_path):
        """Basic prompt filename selects basic processor as fallback."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Test",
                    "start_time": "00:00:00.000",
                    "end_time": "00:01:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "confidence": 0.8,
                    "transcript": "Test",
                }
            ])
        )

        segmenter = self._make_segmenter(
            mock_llm, tmp_path, prompt_filename="segmenter-basic.md"
        )
        assert isinstance(segmenter._processor, BasicTranscriptProcessor)
        assert segmenter.prompt_filename == "segmenter-basic.md"

    @pytest.mark.asyncio
    async def test_capabilities_takes_precedence_over_transcript(self, tmp_path):
        """Explicit capabilities parameter takes precedence over transcript detection."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Test",
                    "start_time": "00:00:00.000",
                    "end_time": "00:01:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "confidence": 0.8,
                    "transcript": "Test",
                }
            ])
        )

        # Transcript has words (would suggest advanced)
        transcript = TranscriptResult(
            text="Hello",
            confidence=0.9,
            words=[WordTimestamp(word="Hello", start=0.0, end=0.5)],
            duration_s=1.0,
            provider="test",
            model="test",
        )
        # But capabilities explicitly say no timestamps
        caps = ProviderCapabilities(has_word_timestamps=False)
        segmenter = self._make_segmenter(
            mock_llm, tmp_path, capabilities=caps, transcript=transcript
        )

        # Capabilities should win
        assert isinstance(segmenter._processor, BasicTranscriptProcessor)
