"""Unit tests for ChapterSegmenter — LLM-based chapter segmentation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.chapter import Chapter
from src.processors.segmenter import ChapterSegmenter, PromptManager, _extract_json_from_response
from src.providers.llm.base import LLMResponse
from src.utils.errors import ProviderError


class TestExtractJSONFromResponse:
    """Test JSON extraction from LLM responses with various formats."""

    def test_extract_direct_json_object(self):
        """Extracts direct JSON object without wrappers."""
        text = '{"key": "value"}'
        result = _extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_extract_direct_json_array(self):
        """Extracts direct JSON array without wrappers."""
        text = '[{"n": 1}, {"n": 2}]'
        result = _extract_json_from_response(text)
        assert len(result) == 2

    def test_extract_json_from_markdown_code_block(self):
        """Extracts JSON from markdown code blocks."""
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_extract_json_from_markdown_without_language(self):
        """Extracts JSON from code block without language specifier."""
        text = '```\n{"key": "value"}\n```'
        result = _extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_extract_json_array_from_markdown(self):
        """Extracts JSON array from markdown code block."""
        text = '```json\n[{"n": 1}]\n```'
        result = _extract_json_from_response(text)
        assert len(result) == 1

    def test_extract_json_with_bracket_matching_array(self):
        """Finds JSON array boundaries via bracket matching."""
        text = '[{"n": 1}] some trailing text'
        result = _extract_json_from_response(text)
        assert len(result) == 1

    def test_extract_json_with_brace_matching_object(self):
        """Finds JSON object boundaries via brace matching."""
        text = '{"key": "value"} extra text'
        result = _extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_extract_nested_json_array(self):
        """Handles nested arrays with bracket matching."""
        text = '[{"items": [1, 2, 3]}]'
        result = _extract_json_from_response(text)
        assert result[0]["items"] == [1, 2, 3]

    def test_extract_nested_json_object(self):
        """Handles nested objects with brace matching."""
        text = '{"outer": {"inner": "value"}}'
        result = _extract_json_from_response(text)
        assert result["outer"]["inner"] == "value"

    def test_extract_invalid_json_raises(self):
        """Raises JSONDecodeError for completely invalid text."""
        with pytest.raises(json.JSONDecodeError):
            _extract_json_from_response("this is not json at all!!!")


class TestPromptManager:
    """Test prompt loading and variable injection."""

    def test_load_prompt_from_file(self, tmp_path):
        """Loads a prompt template from file."""
        prompt_file = tmp_path / "test_prompt.md"
        prompt_file.write_text("Hello {{NAME}}, welcome to {{PLACE}}.")

        manager = PromptManager(prompt_dir=tmp_path)
        template = manager.load("test_prompt.md")

        assert "{{NAME}}" in template
        assert "{{PLACE}}" in template

    def test_load_missing_prompt_raises(self, tmp_path):
        """Raises FileNotFoundError for missing prompt."""
        manager = PromptManager(prompt_dir=tmp_path)

        with pytest.raises(FileNotFoundError):
            manager.load("nonexistent.md")

    def test_load_prompt_cached(self, tmp_path):
        """Caches loaded prompts for performance."""
        prompt_file = tmp_path / "cached.md"
        prompt_file.write_text("Cached content.")

        manager = PromptManager(prompt_dir=tmp_path)
        first = manager.load("cached.md")
        second = manager.load("cached.md")

        assert first is second  # Same cached object

    def test_inject_variables(self, tmp_path):
        """Injects template variables correctly."""
        prompt_file = tmp_path / "inject.md"
        prompt_file.write_text("Title: {{VIDEO_TITLE}}\nTopic: {{VIDEO_TOPIC}}")

        manager = PromptManager(prompt_dir=tmp_path)
        result = manager.load_and_inject(
            "inject.md",
            VIDEO_TITLE="My Video",
            VIDEO_TOPIC="Testing",
        )

        assert "Title: My Video" in result
        assert "Topic: Testing" in result
        assert "{{VIDEO_TITLE}}" not in result

    def test_inject_missing_variable_preserves_placeholder(self, tmp_path):
        """Preserves placeholder when variable not provided."""
        prompt_file = tmp_path / "partial.md"
        prompt_file.write_text("Title: {{VIDEO_TITLE}}\nDuration: {{VIDEO_DURATION}}")

        manager = PromptManager(prompt_dir=tmp_path)
        result = manager.load_and_inject("partial.md", VIDEO_TITLE="Test")

        assert "Title: Test" in result
        assert "{{VIDEO_DURATION}}" in result

    def test_load_malformed_prompt_file(self, tmp_path):
        """Handles empty prompt file gracefully."""
        prompt_file = tmp_path / "empty.md"
        prompt_file.write_text("")

        manager = PromptManager(prompt_dir=tmp_path)
        template = manager.load("empty.md")

        assert template == ""


class TestChapterSegmenterSegmentation:
    """Test ChapterSegmenter segmentation logic."""

    def _make_llm_response(self, chapters_data):
        """Create a mock LLMResponse with chapter data."""
        return LLMResponse(
            text=json.dumps(chapters_data),
            usage={"prompt_tokens": 100, "completion_tokens": 200},
            provider="mock",
            model="mock-model",
        )

    def _make_segmenter(self, mock_llm, tmp_path):
        """Create a segmenter with mock LLM."""
        prompt_file = tmp_path / "segmenter.md"
        prompt_file.write_text("Segment: {{VIDEO_TITLE}}\n{{FULL_TRANSCRIPT}}")

        return ChapterSegmenter(
            llm_provider=mock_llm,
            prompt_manager=PromptManager(prompt_dir=tmp_path),
            prompt_filename="segmenter.md",
        )

    @pytest.mark.asyncio
    async def test_segment_returns_chapters_from_llm(self, tmp_path):
        """Segmentation parses LLM response into Chapter objects."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Introduction",
                    "start_time": "00:00:00.000",
                    "end_time": "00:05:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 300.0,
                    "confidence": 0.92,
                    "transcript": "Welcome to the course.",
                }
            ])
        )

        segmenter = self._make_segmenter(mock_llm, tmp_path)
        chapters = await segmenter.segment(
            transcript="Welcome to the course.",
            video_title="Test Course",
            video_topic="Testing",
            video_total_duration="00:30:00",
        )

        assert len(chapters) == 1
        assert isinstance(chapters[0], Chapter)
        assert chapters[0].number == 1
        assert chapters[0].title == "Introduction"
        assert chapters[0].confidence == 0.92

    @pytest.mark.asyncio
    async def test_segment_multiple_chapters(self, tmp_path):
        """Parses multiple chapters from LLM response."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Intro",
                    "start_time": "00:00:00.000",
                    "end_time": "00:05:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 300.0,
                    "confidence": 0.95,
                    "transcript": "Part one.",
                },
                {
                    "number": 2,
                    "title": "Core",
                    "start_time": "00:05:00.000",
                    "end_time": "00:15:00.000",
                    "start_seconds": 300.0,
                    "end_seconds": 900.0,
                    "confidence": 0.88,
                    "transcript": "Part two.",
                },
            ])
        )

        segmenter = self._make_segmenter(mock_llm, tmp_path)
        chapters = await segmenter.segment(
            transcript="Part one. Part two.",
            video_title="Multi Chapter",
            video_topic="Testing",
            video_total_duration="00:15:00",
        )

        assert len(chapters) == 2
        assert chapters[0].title == "Intro"
        assert chapters[1].title == "Core"

    @pytest.mark.asyncio
    async def test_segment_injects_prompt_variables(self, tmp_path):
        """Segmentation injects variables into prompt template."""
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
                    "confidence": 0.9,
                    "transcript": "Test transcript",
                }
            ])
        )

        segmenter = self._make_segmenter(mock_llm, tmp_path)
        await segmenter.segment(
            transcript="My transcript content",
            video_title="My Video Title",
            video_topic="My Topic",
            video_total_duration="00:10:00",
        )

        # Verify the prompt was constructed with variables
        call_args = mock_llm.generate.call_args
        prompt = call_args[1]["prompt"] if "prompt" in call_args[1] else call_args[0][0]
        assert "My Video Title" in prompt
        assert "My transcript content" in prompt


class TestChapterSegmenterValidation:
    """Test ChapterSegmenter validation and error handling."""

    def _make_llm_response(self, text):
        # text can be a list (auto-json) or a raw string
        if isinstance(text, (list, dict)):
            text = json.dumps(text)
        return LLMResponse(
            text=text,
            usage={"prompt_tokens": 100, "completion_tokens": 200},
            provider="mock",
            model="mock-model",
        )

    def _make_segmenter(self, mock_llm, tmp_path):
        prompt_file = tmp_path / "segmenter.md"
        prompt_file.write_text("Segment: {{VIDEO_TITLE}}\n{{FULL_TRANSCRIPT}}")
        return ChapterSegmenter(
            llm_provider=mock_llm,
            prompt_manager=PromptManager(prompt_dir=tmp_path),
            prompt_filename="segmenter.md",
        )

    @pytest.mark.asyncio
    async def test_malformed_json_retries(self, tmp_path):
        """Retries on malformed JSON response."""
        mock_llm = MagicMock()
        # First call: malformed JSON, second call: valid
        mock_llm.generate = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="{invalid json}",
                    usage={},
                    provider="mock",
                    model="mock-model",
                ),
                self._make_llm_response([
                    {
                        "number": 1,
                        "title": "Retry Success",
                        "start_time": "00:00:00.000",
                        "end_time": "00:01:00.000",
                        "start_seconds": 0.0,
                        "end_seconds": 60.0,
                        "confidence": 0.9,
                        "transcript": "Retry transcript",
                    }
                ]),
            ]
        )

        segmenter = self._make_segmenter(mock_llm, tmp_path)
        chapters = await segmenter.segment(
            transcript="Test",
            video_title="Test",
            video_topic="Test",
            video_total_duration="00:01:00",
        )

        assert len(chapters) == 1
        assert chapters[0].title == "Retry Success"
        assert mock_llm.generate.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises(self, tmp_path):
        """Raises after max retries on persistent malformed JSON."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=LLMResponse(
                text="not json at all",
                usage={},
                provider="mock",
                model="mock-model",
            )
        )

        segmenter = self._make_segmenter(mock_llm, tmp_path)
        segmenter.max_retries = 2

        with pytest.raises(ProviderError):
            await segmenter.segment(
                transcript="Test",
                video_title="Test",
                video_topic="Test",
                video_total_duration="00:01:00",
            )

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises(self, tmp_path):
        """Rejects chapter missing required fields."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Incomplete",
                    # Missing start_time, end_time, start_seconds, end_seconds, confidence, transcript
                }
            ])
        )

        segmenter = self._make_segmenter(mock_llm, tmp_path)

        with pytest.raises(Exception):
            await segmenter.segment(
                transcript="Test",
                video_title="Test",
                video_topic="Test",
                video_total_duration="00:01:00",
            )

    @pytest.mark.asyncio
    async def test_low_confidence_warning(self, tmp_path):
        """Logs warning when segmentation confidence below threshold."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response([
                {
                    "number": 1,
                    "title": "Low Confidence",
                    "start_time": "00:00:00.000",
                    "end_time": "00:01:00.000",
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "confidence": 0.5,
                    "transcript": "Unclear content",
                }
            ])
        )

        segmenter = self._make_segmenter(mock_llm, tmp_path)
        chapters = await segmenter.segment(
            transcript="Unclear content",
            video_title="Test",
            video_topic="Test",
            video_total_duration="00:01:00",
        )

        # Chapter is still returned but with low confidence
        assert len(chapters) == 1
        assert chapters[0].confidence == 0.5
        # needs_review flag should be set
        assert chapters[0].needs_review is True


class TestChapterSegmenterConfidence:
    """Test confidence scoring and needs_review flags."""

    def test_confidence_threshold_default(self):
        """Default segmentation confidence threshold is 0.7."""
        mock_llm = MagicMock()
        segmenter = ChapterSegmenter(llm_provider=mock_llm)
        assert segmenter.confidence_threshold == 0.7

    def test_confidence_threshold_custom(self):
        """Custom confidence threshold is accepted."""
        mock_llm = MagicMock()
        segmenter = ChapterSegmenter(llm_provider=mock_llm, confidence_threshold=0.8)
        assert segmenter.confidence_threshold == 0.8

    def test_needs_review_below_threshold(self, tmp_path):
        """Chapter below threshold gets needs_review=True."""
        from src.processors.segmenter import _check_needs_review

        result = _check_needs_review(0.5, threshold=0.7)
        assert result is True

    def test_needs_review_above_threshold(self, tmp_path):
        """Chapter above threshold gets needs_review=False."""
        from src.processors.segmenter import _check_needs_review

        result = _check_needs_review(0.85, threshold=0.7)
        assert result is False

    def test_needs_review_at_threshold(self, tmp_path):
        """Chapter at exact threshold gets needs_review=False."""
        from src.processors.segmenter import _check_needs_review

        result = _check_needs_review(0.7, threshold=0.7)
        assert result is False
