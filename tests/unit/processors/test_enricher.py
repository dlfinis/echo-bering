"""Unit tests for MetadataEnricher — LLM-based chapter enrichment."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.chapter import Chapter, EnrichedChapter, Highlight
from src.processors.enricher import MetadataEnricher
from src.processors.segmenter import PromptManager
from src.providers.llm.base import LLMResponse
from src.utils.errors import ProviderError


class TestMetadataEnricherEnrichment:
    """Test MetadataEnricher enrichment logic."""

    def _make_chapter(self):
        return Chapter(
            number=1,
            title="Introduction to Python",
            start_time="00:00:00.000",
            end_time="00:05:00.000",
            start_seconds=0.0,
            end_seconds=300.0,
            confidence=0.9,
            transcript="Welcome to this course. Today we will learn Python basics.",
            needs_review=False,
        )

    def _make_llm_response(self, data):
        if isinstance(data, (dict, list)):
            data = json.dumps(data)
        return LLMResponse(
            text=data,
            usage={"prompt_tokens": 200, "completion_tokens": 500},
            provider="mock",
            model="mock-model",
        )

    def _make_valid_enrichment(self, chapter):
        """Create a valid enrichment JSON response."""
        return {
            "chapter": {
                "title": "Introduction to Python",
                "title_seo": "Python Basics: Complete Beginner Guide",
                "slug": "introduction-to-python",
            },
            "content": {
                "description": "This chapter introduces Python fundamentals.",
                "context": "First chapter in the series.",
                "summary_bullets": ["Python is an interpreted language", "Variables and types"],
            },
            "knowledge": {
                "terms_used": [
                    {"term": "Python", "type": "lenguaje", "frequency": 3, "definition": "Programming language"}
                ],
                "key_concepts": ["Variables", "Types"],
                "entities_detected": {
                    "personas": [],
                    "organizaciones": [],
                    "tecnologías": ["Python"],
                    "lenguajes": ["Python"],
                },
            },
            "highlights": [
                {
                    "timestamp": "00:02:30",
                    "type": "insight",
                    "label": "Idea clave",
                    "quote": "Python makes programming accessible.",
                    "importance": "alta",
                }
            ],
            "pedagogy": {
                "difficulty_level": "principiante",
                "prerequisites": ["Basic computer skills"],
                "learning_objectives": ["Understand Python basics"],
                "teaching_methods": ["Demo", "Theory"],
            },
            "confidence": {
                "segmentation_score": 0.92,
                "transcription_quality": 0.88,
                "content_coherence": 0.95,
                "needs_review": False,
                "review_reasons": [],
            },
        }

    def _make_enricher(self, mock_llm, tmp_path):
        """Create an enricher with mock LLM and prompt."""
        prompt_file = tmp_path / "enricher.md"
        prompt_file.write_text(
            "Enrich chapter: {{CHAPTER_NUMBER}} of {{TOTAL_CHAPTERS}}\n"
            "Title: {{VIDEO_TITLE}}\n"
            "Topic: {{VIDEO_TOPIC}}\n"
            "Duration: {{VIDEO_TOTAL_DURATION}}\n"
            "Chapter range: {{CHAPTER_START}} - {{CHAPTER_END}}\n"
            "Previous: {{PREV_CHAPTER_TITLE}}\n"
            "Next: {{NEXT_CHAPTER_TITLE}}\n"
            "Transcript: {{CHAPTER_TRANSCRIPT}}"
        )
        return MetadataEnricher(
            llm_provider=mock_llm,
            prompt_manager=PromptManager(prompt_dir=tmp_path),
            prompt_filename="enricher.md",
        )

    @pytest.mark.asyncio
    async def test_enrich_single_chapter(self, tmp_path):
        """Enrichment returns EnrichedChapter from LLM response."""
        chapter = self._make_chapter()
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=self._make_llm_response(self._make_valid_enrichment(chapter))
        )

        enricher = self._make_enricher(mock_llm, tmp_path)
        result = await enricher.enrich(
            chapter=chapter,
            video_title="Python Course",
            video_topic="Python Basics",
            video_total_duration="00:30:00",
            total_chapters=5,
            prev_chapter_title=None,
            next_chapter_title="Variables and Types",
        )

        assert isinstance(result, EnrichedChapter)
        assert result.chapter.number == 1
        assert result.description == "This chapter introduces Python fundamentals."
        assert len(result.summary_bullets) == 2
        assert len(result.highlights) == 1

    @pytest.mark.asyncio
    async def test_enrich_injects_prompt_variables(self, tmp_path):
        """Enrichment injects all chapter and video context variables."""
        chapter = self._make_chapter()
        captured_prompt = None

        async def capture_generate(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return self._make_llm_response(self._make_valid_enrichment(chapter))

        mock_llm = MagicMock()
        mock_llm.generate = capture_generate

        enricher = self._make_enricher(mock_llm, tmp_path)
        await enricher.enrich(
            chapter=chapter,
            video_title="Python Course",
            video_topic="Python Basics",
            video_total_duration="00:30:00",
            total_chapters=5,
            prev_chapter_title=None,
            next_chapter_title="Variables",
        )

        assert "Python Course" in captured_prompt
        assert "Welcome to this course" in captured_prompt
        assert "1" in captured_prompt  # chapter number
        assert "5" in captured_prompt  # total chapters

    @pytest.mark.asyncio
    async def test_enrich_handles_adjacent_chapters(self, tmp_path):
        """Enrichment passes adjacent chapter titles for context."""
        chapter = self._make_chapter()
        captured_prompt = None

        async def capture_generate(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return self._make_llm_response(self._make_valid_enrichment(chapter))

        mock_llm = MagicMock()
        mock_llm.generate = capture_generate

        enricher = self._make_enricher(mock_llm, tmp_path)
        await enricher.enrich(
            chapter=chapter,
            video_title="Test",
            video_topic="Test",
            video_total_duration="00:10:00",
            total_chapters=3,
            prev_chapter_title="Setup",
            next_chapter_title="Advanced",
        )

        assert "Setup" in captured_prompt
        assert "Advanced" in captured_prompt

    @pytest.mark.asyncio
    async def test_enrich_empty_adjacent_chapters(self, tmp_path):
        """Enrichment uses N/A for missing adjacent chapters."""
        chapter = self._make_chapter()
        captured_prompt = None

        async def capture_generate(prompt, **kwargs):
            nonlocal captured_prompt
            captured_prompt = prompt
            return self._make_llm_response(self._make_valid_enrichment(chapter))

        mock_llm = MagicMock()
        mock_llm.generate = capture_generate

        enricher = self._make_enricher(mock_llm, tmp_path)
        await enricher.enrich(
            chapter=chapter,
            video_title="Test",
            video_topic="Test",
            video_total_duration="00:10:00",
            total_chapters=1,
            prev_chapter_title=None,
            next_chapter_title=None,
        )

        assert "N/A" in captured_prompt


class TestMetadataEnricherValidation:
    """Test MetadataEnricher validation and error handling."""

    def _make_chapter(self):
        return Chapter(
            number=1,
            title="Test",
            start_time="00:00:00.000",
            end_time="00:01:00.000",
            start_seconds=0.0,
            end_seconds=60.0,
            confidence=0.9,
            transcript="Test transcript",
            needs_review=False,
        )

    def _make_enricher(self, mock_llm, tmp_path):
        prompt_file = tmp_path / "enricher.md"
        prompt_file.write_text(
            "Enrich: {{CHAPTER_NUMBER}}\n"
            "Prev: {{PREV_CHAPTER_TITLE}}\n"
            "Next: {{NEXT_CHAPTER_TITLE}}\n"
            "Transcript: {{CHAPTER_TRANSCRIPT}}"
        )
        return MetadataEnricher(
            llm_provider=mock_llm,
            prompt_manager=PromptManager(prompt_dir=tmp_path),
            prompt_filename="enricher.md",
        )

    @pytest.mark.asyncio
    async def test_malformed_json_retries(self, tmp_path):
        """Retries on malformed JSON from LLM."""
        chapter = self._make_chapter()
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            side_effect=[
                LLMResponse(
                    text="{bad json",
                    usage={},
                    provider="mock",
                    model="mock-model",
                ),
                LLMResponse(
                    text=json.dumps({
                        "chapter": {"title": "Retry", "title_seo": "Retry", "slug": "retry"},
                        "content": {"description": "D", "context": "C", "summary_bullets": ["B"]},
                        "knowledge": {"terms_used": [], "key_concepts": [], "entities_detected": {}},
                        "highlights": [],
                        "pedagogy": {"difficulty_level": "principiante", "prerequisites": [], "learning_objectives": [], "teaching_methods": []},
                        "confidence": {"segmentation_score": 0.8, "transcription_quality": 0.8, "content_coherence": 0.8, "needs_review": False, "review_reasons": []},
                    }),
                    usage={},
                    provider="mock",
                    model="mock-model",
                ),
            ]
        )

        enricher = self._make_enricher(mock_llm, tmp_path)
        result = await enricher.enrich(
            chapter=chapter,
            video_title="Test",
            video_topic="Test",
            video_total_duration="00:01:00",
            total_chapters=1,
            prev_chapter_title=None,
            next_chapter_title=None,
        )

        assert isinstance(result, EnrichedChapter)
        assert mock_llm.generate.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_raises(self, tmp_path):
        """Raises after max retries on persistent malformed JSON."""
        chapter = self._make_chapter()
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=LLMResponse(
                text="not json",
                usage={},
                provider="mock",
                model="mock-model",
            )
        )

        enricher = self._make_enricher(mock_llm, tmp_path)
        enricher.max_retries = 2

        with pytest.raises(ProviderError):
            await enricher.enrich(
                chapter=chapter,
                video_title="Test",
                video_topic="Test",
                video_total_duration="00:01:00",
                total_chapters=1,
                prev_chapter_title=None,
                next_chapter_title=None,
            )

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises(self, tmp_path):
        """Rejects enrichment missing required fields."""
        chapter = self._make_chapter()
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=LLMResponse(
                text=json.dumps({
                    "chapter": {"title": "Incomplete"},
                    # Missing content, knowledge, highlights, pedagogy, confidence
                }),
                usage={},
                provider="mock",
                model="mock-model",
            )
        )

        enricher = self._make_enricher(mock_llm, tmp_path)

        with pytest.raises(Exception):
            await enricher.enrich(
                chapter=chapter,
                video_title="Test",
                video_topic="Test",
                video_total_duration="00:01:00",
                total_chapters=1,
                prev_chapter_title=None,
                next_chapter_title=None,
            )


class TestMetadataEnricherConfidence:
    """Test confidence scoring for enriched chapters."""

    def _make_chapter(self):
        return Chapter(
            number=1,
            title="Test",
            start_time="00:00:00.000",
            end_time="00:01:00.000",
            start_seconds=0.0,
            end_seconds=60.0,
            confidence=0.9,
            transcript="Test transcript",
            needs_review=False,
        )

    def _make_enricher(self, mock_llm, tmp_path):
        prompt_file = tmp_path / "enricher.md"
        prompt_file.write_text(
            "Enrich: {{CHAPTER_NUMBER}}\n"
            "Prev: {{PREV_CHAPTER_TITLE}}\n"
            "Next: {{NEXT_CHAPTER_TITLE}}\n"
            "Transcript: {{CHAPTER_TRANSCRIPT}}"
        )
        return MetadataEnricher(
            llm_provider=mock_llm,
            prompt_manager=PromptManager(prompt_dir=tmp_path),
            prompt_filename="enricher.md",
        )

    @pytest.mark.asyncio
    async def test_low_content_coherence_flags_review(self, tmp_path):
        """Low content_coherence score triggers needs_review."""
        chapter = self._make_chapter()
        enrichment = {
            "chapter": {"title": "Test", "title_seo": "Test", "slug": "test"},
            "content": {"description": "D", "context": "C", "summary_bullets": []},
            "knowledge": {"terms_used": [], "key_concepts": [], "entities_detected": {}},
            "highlights": [],
            "pedagogy": {"difficulty_level": "principiante", "prerequisites": [], "learning_objectives": [], "teaching_methods": []},
            "confidence": {
                "segmentation_score": 0.9,
                "transcription_quality": 0.9,
                "content_coherence": 0.4,  # Below threshold
                "needs_review": True,
                "review_reasons": ["Low content coherence"],
            },
        }

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=LLMResponse(
                text=json.dumps(enrichment),
                usage={},
                provider="mock",
                model="mock-model",
            )
        )

        enricher = self._make_enricher(mock_llm, tmp_path)
        result = await enricher.enrich(
            chapter=chapter,
            video_title="Test",
            video_topic="Test",
            video_total_duration="00:01:00",
            total_chapters=1,
            prev_chapter_title=None,
            next_chapter_title=None,
        )

        assert result.confidence["content_coherence"] == 0.4
        assert result.confidence["needs_review"] is True

    @pytest.mark.asyncio
    async def test_transcription_quality_below_threshold(self, tmp_path):
        """Low transcription_quality triggers needs_review."""
        chapter = self._make_chapter()
        enrichment = {
            "chapter": {"title": "Test", "title_seo": "Test", "slug": "test"},
            "content": {"description": "D", "context": "C", "summary_bullets": []},
            "knowledge": {"terms_used": [], "key_concepts": [], "entities_detected": {}},
            "highlights": [],
            "pedagogy": {"difficulty_level": "principiante", "prerequisites": [], "learning_objectives": [], "teaching_methods": []},
            "confidence": {
                "segmentation_score": 0.9,
                "transcription_quality": 0.3,  # Very low
                "content_coherence": 0.9,
                "needs_review": True,
                "review_reasons": ["Poor transcription quality"],
            },
        }

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=LLMResponse(
                text=json.dumps(enrichment),
                usage={},
                provider="mock",
                model="mock-model",
            )
        )

        enricher = self._make_enricher(mock_llm, tmp_path)
        result = await enricher.enrich(
            chapter=chapter,
            video_title="Test",
            video_topic="Test",
            video_total_duration="00:01:00",
            total_chapters=1,
            prev_chapter_title=None,
            next_chapter_title=None,
        )

        assert result.confidence["needs_review"] is True


class TestEnrichedChapterModelDump:
    """Test EnrichedChapter model_dump produces correct metadata.json structure."""

    def _make_chapter(self):
        return Chapter(
            number=2,
            title="Advanced Concepts",
            start_time="00:10:00.000",
            end_time="00:20:00.000",
            start_seconds=600.0,
            end_seconds=1200.0,
            confidence=0.88,
            transcript="Advanced content here with many words for counting.",
            needs_review=False,
        )

    def test_model_dump_produces_metadata_structure(self, tmp_path):
        """model_dump returns the arch-vision.md metadata.json structure."""
        chapter = self._make_chapter()
        enriched = EnrichedChapter(
            chapter=chapter,
            description="Deep dive into advanced topics.",
            context="Follows introduction chapter.",
            summary_bullets=["Concept A", "Concept B"],
            terms_used=[{"term": "OOP", "type": "concepto", "frequency": 5, "definition": "Object-oriented programming"}],
            key_concepts=["Polymorphism", "Inheritance"],
            entities_detected={"personas": ["Grace Hopper"], "organizaciones": [], "tecnologías": ["Python"], "lenguajes": ["Python"]},
            highlights=[
                Highlight(
                    timestamp="00:15:30",
                    type="insight",
                    label="Idea clave",
                    quote="OOP is powerful.",
                    importance="alta",
                )
            ],
            pedagogy={
                "difficulty_level": "avanzado",
                "prerequisites": ["Python basics"],
                "learning_objectives": ["Master OOP patterns"],
                "teaching_methods": ["Code examples"],
            },
            confidence={
                "segmentation_score": 0.88,
                "transcription_quality": 0.85,
                "content_coherence": 0.92,
                "needs_review": False,
                "review_reasons": [],
            },
        )

        metadata = enriched.model_dump()

        # Verify top-level keys match arch-vision.md schema
        assert "chapter" in metadata
        assert "timing" in metadata
        assert "content" in metadata
        assert "knowledge" in metadata
        assert "highlights" in metadata
        assert "pedagogy" in metadata
        assert "confidence" in metadata

        # Verify chapter structure
        assert metadata["chapter"]["number"] == 2
        assert metadata["chapter"]["title"] == "Advanced Concepts"
        assert metadata["chapter"]["title_seo"] == "Advanced Concepts"  # falls back to title
        assert metadata["chapter"]["slug"] == "advanced-concepts"

        # Verify timing
        assert metadata["timing"]["start_time"] == "00:10:00.000"
        assert metadata["timing"]["end_time"] == "00:20:00.000"
        assert metadata["timing"]["duration_seconds"] == 600
        assert metadata["timing"]["word_count"] > 0

        # Verify content
        assert metadata["content"]["description"] == "Deep dive into advanced topics."
        assert metadata["content"]["summary_bullets"] == ["Concept A", "Concept B"]

        # Verify knowledge
        assert len(metadata["knowledge"]["terms_used"]) == 1
        assert metadata["knowledge"]["key_concepts"] == ["Polymorphism", "Inheritance"]

        # Verify confidence
        assert metadata["confidence"]["segmentation_score"] == 0.88
        assert metadata["confidence"]["needs_review"] is False
