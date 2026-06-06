"""Unit tests for Chapter domain models."""

import pytest

from src.models.chapter import Chapter, EnrichedChapter, Highlight


class TestChapter:
    """Test Chapter Pydantic model."""

    def test_chapter_creation_with_valid_data(self):
        """Creates a Chapter with all required fields."""
        chapter = Chapter(
            number=1,
            title="Introduction",
            start_time="00:00:00.000",
            end_time="00:05:30.000",
            start_seconds=0.0,
            end_seconds=330.0,
            confidence=0.92,
            transcript="This is the intro transcript.",
        )

        assert chapter.number == 1
        assert chapter.title == "Introduction"
        assert chapter.start_time == "00:00:00.000"
        assert chapter.end_time == "00:05:30.000"
        assert chapter.start_seconds == 0.0
        assert chapter.end_seconds == 330.0
        assert chapter.confidence == 0.92
        assert chapter.transcript == "This is the intro transcript."

    def test_chapter_confidence_bounds(self):
        """Rejects confidence outside 0-1 range."""
        with pytest.raises(Exception):
            Chapter(
                number=1,
                title="Test",
                start_time="00:00:00.000",
                end_time="00:01:00.000",
                start_seconds=0.0,
                end_seconds=60.0,
                confidence=1.5,
                transcript="test",
            )

    def test_chapter_negative_confidence_rejected(self):
        """Rejects negative confidence."""
        with pytest.raises(Exception):
            Chapter(
                number=1,
                title="Test",
                start_time="00:00:00.000",
                end_time="00:01:00.000",
                start_seconds=0.0,
                end_seconds=60.0,
                confidence=-0.1,
                transcript="test",
            )

    def test_chapter_model_dump_produces_dict(self):
        """model_dump returns a serializable dict."""
        chapter = Chapter(
            number=2,
            title="Core Concepts",
            start_time="00:05:30.000",
            end_time="00:15:00.000",
            start_seconds=330.0,
            end_seconds=900.0,
            confidence=0.85,
            transcript="Deep dive into concepts.",
        )

        data = chapter.model_dump()
        assert isinstance(data, dict)
        assert data["number"] == 2
        assert data["title"] == "Core Concepts"
        assert data["confidence"] == 0.85

    def test_chapter_from_dict(self):
        """Creates Chapter from a dict (LLM response parsing)."""
        data = {
            "number": 3,
            "title": "Advanced Topics",
            "start_time": "00:15:00.000",
            "end_time": "00:25:00.000",
            "start_seconds": 900.0,
            "end_seconds": 1500.0,
            "confidence": 0.78,
            "transcript": "Advanced content here.",
        }

        chapter = Chapter(**data)
        assert chapter.number == 3
        assert chapter.title == "Advanced Topics"


class TestHighlight:
    """Test Highlight Pydantic model."""

    def test_highlight_creation(self):
        """Creates a Highlight with all required fields."""
        highlight = Highlight(
            timestamp="00:03:45",
            type="insight",
            label="Idea clave",
            quote="This is a key insight from the video.",
            importance="alta",
        )

        assert highlight.timestamp == "00:03:45"
        assert highlight.type == "insight"
        assert highlight.label == "Idea clave"
        assert highlight.quote == "This is a key insight from the video."
        assert highlight.importance == "alta"

    def test_highlight_valid_types(self):
        """Accepts all valid highlight types."""
        valid_types = [
            "insight", "example", "warning", "takeaway",
            "hook", "controversial", "definition", "demo",
        ]
        for h_type in valid_types:
            highlight = Highlight(
                timestamp="00:01:00",
                type=h_type,
                label="Test label",
                quote="Test quote",
                importance="media",
            )
            assert highlight.type == h_type

    def test_highlight_valid_importance(self):
        """Accepts valid importance levels."""
        for importance in ["alta", "media", "baja"]:
            highlight = Highlight(
                timestamp="00:01:00",
                type="insight",
                label="Test",
                quote="Test",
                importance=importance,
            )
            assert highlight.importance == importance


class TestEnrichedChapter:
    """Test EnrichedChapter Pydantic model."""

    def _make_chapter(self):
        return Chapter(
            number=1,
            title="Intro",
            start_time="00:00:00.000",
            end_time="00:05:00.000",
            start_seconds=0.0,
            end_seconds=300.0,
            confidence=0.9,
            transcript="Intro transcript",
        )

    def test_enriched_chapter_creation(self):
        """Creates EnrichedChapter with all fields."""
        chapter = self._make_chapter()
        enriched = EnrichedChapter(
            chapter=chapter,
            description="A description of the chapter.",
            context="Context about this chapter.",
            summary_bullets=["Point 1", "Point 2"],
            terms_used=[{"term": "Pydantic", "type": "framework", "frequency": 3, "definition": "Data validation library"}],
            key_concepts=["Data validation", "Type hints"],
            entities_detected={"personas": [], "organizaciones": [], "tecnologías": ["Pydantic"], "lenguajes": ["Python"]},
            highlights=[
                Highlight(
                    timestamp="00:02:30",
                    type="insight",
                    label="Idea clave",
                    quote="Pydantic validates data at runtime.",
                    importance="alta",
                )
            ],
            pedagogy={
                "difficulty_level": "intermedio",
                "prerequisites": ["Python basics"],
                "learning_objectives": ["Understand Pydantic models"],
                "teaching_methods": ["Demo"],
            },
            confidence={
                "segmentation_score": 0.9,
                "transcription_quality": 0.85,
                "content_coherence": 0.95,
                "needs_review": False,
                "review_reasons": [],
            },
        )

        assert enriched.chapter.number == 1
        assert enriched.description == "A description of the chapter."
        assert len(enriched.summary_bullets) == 2
        assert len(enriched.highlights) == 1
        assert enriched.confidence["segmentation_score"] == 0.9
        assert enriched.confidence["needs_review"] is False

    def test_enriched_chapter_empty_collections(self):
        """Accepts empty arrays for optional collections."""
        chapter = self._make_chapter()
        enriched = EnrichedChapter(
            chapter=chapter,
            description="Description",
            context="Context",
            summary_bullets=[],
            terms_used=[],
            key_concepts=[],
            entities_detected={},
            highlights=[],
            pedagogy={
                "difficulty_level": "principiante",
                "prerequisites": [],
                "learning_objectives": [],
                "teaching_methods": [],
            },
            confidence={
                "segmentation_score": 0.5,
                "transcription_quality": 0.5,
                "content_coherence": 0.5,
                "needs_review": True,
                "review_reasons": ["Low confidence scores"],
            },
        )

        assert enriched.summary_bullets == []
        assert enriched.highlights == []
        assert enriched.confidence["needs_review"] is True
        assert len(enriched.confidence["review_reasons"]) == 1

    def test_enriched_chapter_model_dump(self):
        """model_dump produces full serializable dict."""
        chapter = self._make_chapter()
        enriched = EnrichedChapter(
            chapter=chapter,
            description="Test description",
            context="Test context",
            summary_bullets=["Bullet 1"],
            terms_used=[],
            key_concepts=["Concept 1"],
            entities_detected={"personas": ["John"]},
            highlights=[],
            pedagogy={
                "difficulty_level": "avanzado",
                "prerequisites": ["Advanced Python"],
                "learning_objectives": ["Master advanced topics"],
                "teaching_methods": ["Theory"],
            },
            confidence={
                "segmentation_score": 0.88,
                "transcription_quality": 0.92,
                "content_coherence": 0.85,
                "needs_review": False,
                "review_reasons": [],
            },
        )

        data = enriched.model_dump()
        assert data["chapter"]["title"] == "Intro"
        assert data["content"]["description"] == "Test description"
        assert data["knowledge"]["key_concepts"] == ["Concept 1"]
        assert data["confidence"]["segmentation_score"] == 0.88
