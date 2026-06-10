"""Unit tests for progress events and TUI data structures."""

import pytest

from src.utils.progress import (
    ProgressEvent,
    ProgressEventType,
    PipelineState,
    format_cost,
    format_eta,
)


class TestProgressEventType:
    """Test ProgressEventType enum values."""

    def test_all_event_types_exist(self):
        """All expected event types are defined."""
        assert ProgressEventType.STAGE_START == "stage_start"
        assert ProgressEventType.STAGE_PROGRESS == "stage_progress"
        assert ProgressEventType.STAGE_COMPLETE == "stage_complete"
        assert ProgressEventType.STAGE_ERROR == "stage_error"
        assert ProgressEventType.COST_UPDATE == "cost_update"
        assert ProgressEventType.WARNING == "warning"
        assert ProgressEventType.CHAPTER_COMPLETE == "chapter_complete"


class TestProgressEvent:
    """Test ProgressEvent dataclass."""

    def test_stage_start_event(self):
        """Stage start event has correct fields."""
        event = ProgressEvent(
            type=ProgressEventType.STAGE_START,
            stage="transcribe",
            stage_index=1,
            total_stages=5,
        )

        assert event.type == ProgressEventType.STAGE_START
        assert event.stage == "transcribe"
        assert event.stage_index == 1
        assert event.total_stages == 5
        assert event.progress == 0.0
        assert event.message == ""

    def test_stage_progress_event(self):
        """Stage progress event carries percentage and ETA."""
        event = ProgressEvent(
            type=ProgressEventType.STAGE_PROGRESS,
            stage="transcribe",
            progress=0.65,
            eta_seconds=120,
            message="Processing chunk 3 of 5",
        )

        assert event.progress == 0.65
        assert event.eta_seconds == 120
        assert event.message == "Processing chunk 3 of 5"

    def test_stage_complete_event(self):
        """Stage complete event carries duration."""
        event = ProgressEvent(
            type=ProgressEventType.STAGE_COMPLETE,
            stage="extract",
            duration_seconds=45.2,
        )

        assert event.type == ProgressEventType.STAGE_COMPLETE
        assert event.duration_seconds == 45.2

    def test_error_event(self):
        """Error event carries exception details."""
        event = ProgressEvent(
            type=ProgressEventType.STAGE_ERROR,
            stage="transcribe",
            message="ProviderError: rate limit exceeded",
            error_type="ProviderError",
        )

        assert event.type == ProgressEventType.STAGE_ERROR
        assert event.error_type == "ProviderError"
        assert "rate limit" in event.message

    def test_cost_update_event(self):
        """Cost update event carries cost data."""
        event = ProgressEvent(
            type=ProgressEventType.COST_UPDATE,
            stage="enrich",
            cost_usd=1.25,
            budget_usd=10.0,
        )

        assert event.cost_usd == 1.25
        assert event.budget_usd == 10.0

    def test_warning_event(self):
        """Warning event carries warning details."""
        event = ProgressEvent(
            type=ProgressEventType.WARNING,
            message="Chapter 'Intro' confidence 0.65 < 0.7",
            chapter_slug="intro",
        )

        assert event.type == ProgressEventType.WARNING
        assert event.chapter_slug == "intro"
        assert "0.65" in event.message

    def test_chapter_complete_event(self):
        """Chapter complete event carries chapter info."""
        event = ProgressEvent(
            type=ProgressEventType.CHAPTER_COMPLETE,
            chapter_slug="introduction",
            chapter_number=1,
            total_chapters=5,
        )

        assert event.chapter_slug == "introduction"
        assert event.chapter_number == 1
        assert event.total_chapters == 5

    def test_default_values(self):
        """ProgressEvent has sensible defaults."""
        event = ProgressEvent(type=ProgressEventType.STAGE_START)

        assert event.progress == 0.0
        assert event.message == ""
        assert event.stage == ""
        assert event.stage_index == 0
        assert event.total_stages == 0
        assert event.eta_seconds is None
        assert event.duration_seconds is None
        assert event.cost_usd == 0.0
        assert event.budget_usd == 0.0
        assert event.chapter_slug == ""
        assert event.chapter_number == 0
        assert event.total_chapters == 0
        assert event.error_type is None


class TestPipelineState:
    """Test PipelineState dataclass."""

    def test_initial_state(self):
        """PipelineState starts with default values."""
        state = PipelineState()

        assert state.current_stage == ""
        assert state.stage_index == 0
        assert state.total_stages == 0
        assert state.stage_progress == 0.0
        assert state.total_cost == 0.0
        assert state.budget == 0.0
        assert state.warnings == []
        assert state.errors == []
        assert state.chapters_completed == 0
        assert state.is_running is False
        assert state.is_complete is False
        assert state.is_failed is False

    def test_update_from_stage_start(self):
        """PipelineState updates from STAGE_START event."""
        state = PipelineState()
        event = ProgressEvent(
            type=ProgressEventType.STAGE_START,
            stage="transcribe",
            stage_index=2,
            total_stages=5,
        )

        state.apply(event)

        assert state.current_stage == "transcribe"
        assert state.stage_index == 2
        assert state.total_stages == 5
        assert state.is_running is True

    def test_update_from_stage_progress(self):
        """PipelineState updates progress from STAGE_PROGRESS event."""
        state = PipelineState()
        event = ProgressEvent(
            type=ProgressEventType.STAGE_PROGRESS,
            stage="transcribe",
            progress=0.75,
            eta_seconds=90,
        )

        state.apply(event)

        assert state.stage_progress == 0.75
        assert state.eta_seconds == 90

    def test_update_from_cost_update(self):
        """PipelineState tracks cumulative cost from events."""
        state = PipelineState(budget=10.0)

        state.apply(ProgressEvent(
            type=ProgressEventType.COST_UPDATE,
            cost_usd=1.0,
            budget_usd=10.0,
        ))
        state.apply(ProgressEvent(
            type=ProgressEventType.COST_UPDATE,
            cost_usd=3.5,  # cumulative cost
            budget_usd=10.0,
        ))

        assert state.total_cost == 3.5
        assert state.budget == 10.0

    def test_update_from_warning(self):
        """PipelineState accumulates warnings."""
        state = PipelineState()

        state.apply(ProgressEvent(
            type=ProgressEventType.WARNING,
            message="Low confidence on chapter 1",
            chapter_slug="intro",
        ))

        assert len(state.warnings) == 1
        assert "Low confidence" in state.warnings[0]

    def test_update_from_error(self):
        """PipelineState marks as failed on error."""
        state = PipelineState()

        state.apply(ProgressEvent(
            type=ProgressEventType.STAGE_ERROR,
            stage="transcribe",
            message="ProviderError",
            error_type="ProviderError",
        ))

        assert len(state.errors) == 1
        assert state.is_failed is True
        assert state.is_running is False

    def test_update_from_stage_complete(self):
        """PipelineState marks complete after final stage."""
        state = PipelineState(total_stages=5)
        state.stage_index = 4  # About to complete stage 5

        state.apply(ProgressEvent(
            type=ProgressEventType.STAGE_COMPLETE,
            stage="materialize",
            duration_seconds=30.0,
        ))

        assert state.is_complete is True
        assert state.is_running is False

    def test_update_from_stage_complete_not_final(self):
        """PipelineState continues after non-final stage."""
        state = PipelineState(total_stages=5)

        # Start stage 3 (index 2)
        state.apply(ProgressEvent(
            type=ProgressEventType.STAGE_START,
            stage="segment",
            stage_index=2,
            total_stages=5,
        ))
        # Complete stage 3
        state.apply(ProgressEvent(
            type=ProgressEventType.STAGE_COMPLETE,
            stage="segment",
            duration_seconds=15.0,
        ))

        assert state.is_complete is False
        assert state.is_running is True

    def test_update_from_chapter_complete(self):
        """PipelineState tracks chapter completion count."""
        state = PipelineState()

        for i in range(3):
            state.apply(ProgressEvent(
                type=ProgressEventType.CHAPTER_COMPLETE,
                chapter_slug=f"chapter-{i}",
                chapter_number=i + 1,
                total_chapters=5,
            ))

        assert state.chapters_completed == 3


class TestFormatHelpers:
    """Test formatting helper functions."""

    def test_format_cost_zero(self):
        """Zero cost formats as $0.00."""
        assert format_cost(0.0) == "$0.00"

    def test_format_cost_small(self):
        """Small cost formats correctly."""
        assert format_cost(1.25) == "$1.25"

    def test_format_cost_large(self):
        """Large cost formats correctly."""
        assert format_cost(123.45) == "$123.45"

    def test_format_eta_none(self):
        """None ETA formats as '--'."""
        assert format_eta(None) == "--"

    def test_format_eta_seconds(self):
        """ETA under 60 seconds formats as Ns."""
        assert format_eta(30) == "30s"

    def test_format_eta_minutes(self):
        """ETA over 60 seconds formats as Nm."""
        assert format_eta(120) == "2m"

    def test_format_eta_minutes_seconds(self):
        """ETA with remainder formats as Nm Ns."""
        assert format_eta(150) == "2m 30s"

    def test_format_eta_hours(self):
        """ETA over 3600 seconds formats as Nh Nm."""
        assert format_eta(7500) == "2h 5m"
