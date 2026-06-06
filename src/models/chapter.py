"""Chapter domain models for segmentation and enrichment.

Chapter represents a single video chapter with timing and transcript.
EnrichedChapter extends Chapter with metadata, knowledge extraction,
highlights, and pedagogical analysis.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class Chapter(BaseModel):
    """A single chapter segment from video segmentation."""

    number: int
    title: str
    start_time: str  # HH:MM:SS.mmm
    end_time: str  # HH:MM:SS.mmm
    start_seconds: float
    end_seconds: float
    confidence: float = Field(ge=0, le=1)
    transcript: str
    needs_review: bool = False


class Highlight(BaseModel):
    """A notable highlight within a chapter."""

    timestamp: str  # HH:MM:SS (absolute in video)
    type: str  # insight, example, warning, takeaway, hook, controversial, definition, demo
    label: str
    quote: str
    importance: str  # alta, media, baja

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {"insight", "example", "warning", "takeaway", "hook", "controversial", "definition", "demo"}
        if v not in valid:
            raise ValueError(f"Invalid highlight type: {v}. Must be one of {valid}")
        return v

    @field_validator("importance")
    @classmethod
    def validate_importance(cls, v: str) -> str:
        valid = {"alta", "media", "baja"}
        if v not in valid:
            raise ValueError(f"Invalid importance: {v}. Must be one of {valid}")
        return v


class EnrichedChapter(BaseModel):
    """Chapter enriched with metadata, knowledge, and pedagogical analysis."""

    chapter: Chapter
    description: str
    context: str
    summary_bullets: List[str]
    terms_used: List[Dict[str, Any]]
    key_concepts: List[str]
    entities_detected: Dict[str, List[str]]
    highlights: List[Highlight]
    pedagogy: Dict[str, Any]
    confidence: Dict[str, Any]

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:
        """Dump as metadata.json structure matching arch-vision.md schema."""
        data = super().model_dump(**kwargs)

        # Restructure into the expected metadata.json format
        return {
            "chapter": {
                "number": data["chapter"]["number"],
                "title": data["chapter"]["title"],
                "title_seo": data.get("chapter", {}).get("title_seo", data["chapter"]["title"]),
                "slug": data.get("chapter", {}).get("slug", data["chapter"]["title"].lower().replace(" ", "-")),
            },
            "timing": {
                "start_time": data["chapter"]["start_time"],
                "end_time": data["chapter"]["end_time"],
                "duration_seconds": int(data["chapter"]["end_seconds"] - data["chapter"]["start_seconds"]),
                "word_count": len(data["chapter"]["transcript"].split()),
            },
            "content": {
                "description": data["description"],
                "context": data["context"],
                "summary_bullets": data["summary_bullets"],
            },
            "knowledge": {
                "terms_used": data["terms_used"],
                "key_concepts": data["key_concepts"],
                "entities_detected": data["entities_detected"],
            },
            "highlights": data["highlights"],
            "pedagogy": data["pedagogy"],
            "confidence": data["confidence"],
        }
