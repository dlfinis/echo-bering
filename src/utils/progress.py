"""Progress events and pipeline state for TUI display.

ProgressEvent represents a single pipeline event (stage change, progress,
error, warning, etc.). PipelineState accumulates events to maintain the
current display state.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ProgressEventType(str, Enum):
    """Types of progress events emitted by the pipeline."""

    STAGE_START = "stage_start"
    STAGE_PROGRESS = "stage_progress"
    STAGE_COMPLETE = "stage_complete"
    STAGE_ERROR = "stage_error"
    COST_UPDATE = "cost_update"
    WARNING = "warning"
    CHAPTER_COMPLETE = "chapter_complete"


@dataclass
class ProgressEvent:
    """A single event in the pipeline lifecycle."""

    type: ProgressEventType
    stage: str = ""
    stage_index: int = 0
    total_stages: int = 0
    progress: float = 0.0
    eta_seconds: Optional[float] = None
    duration_seconds: Optional[float] = None
    message: str = ""
    cost_usd: float = 0.0
    budget_usd: float = 0.0
    chapter_slug: str = ""
    chapter_number: int = 0
    total_chapters: int = 0
    error_type: Optional[str] = None


@dataclass
class PipelineState:
    """Accumulated state of the pipeline for TUI rendering."""

    current_stage: str = ""
    stage_index: int = 0
    total_stages: int = 0
    stage_progress: float = 0.0
    eta_seconds: Optional[float] = None
    total_cost: float = 0.0
    budget: float = 0.0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    chapters_completed: int = 0
    is_running: bool = False
    is_complete: bool = False
    is_failed: bool = False

    def apply(self, event: ProgressEvent) -> None:
        """Apply a progress event to update state.

        Args:
            event: The progress event to apply.
        """
        if event.type == ProgressEventType.STAGE_START:
            self.current_stage = event.stage
            self.stage_index = event.stage_index
            self.total_stages = event.total_stages
            self.stage_progress = 0.0
            self.is_running = True
            self.is_complete = False
            self.is_failed = False

        elif event.type == ProgressEventType.STAGE_PROGRESS:
            self.stage_progress = event.progress
            self.eta_seconds = event.eta_seconds

        elif event.type == ProgressEventType.STAGE_COMPLETE:
            self.stage_progress = 1.0
            self.eta_seconds = None
            # Check if this was the final stage
            if self.stage_index >= self.total_stages - 1 and self.total_stages > 0:
                self.is_complete = True
                self.is_running = False
            # Non-final stage complete — stay running

        elif event.type == ProgressEventType.STAGE_ERROR:
            self.errors.append(event.message)
            self.is_running = False
            self.is_failed = True

        elif event.type == ProgressEventType.COST_UPDATE:
            self.total_cost = event.cost_usd
            self.budget = event.budget_usd

        elif event.type == ProgressEventType.WARNING:
            self.warnings.append(event.message)

        elif event.type == ProgressEventType.CHAPTER_COMPLETE:
            self.chapters_completed = event.chapter_number


def format_cost(amount: float) -> str:
    """Format a cost amount as a dollar string.

    Args:
        amount: Cost in USD.

    Returns:
        Formatted string like "$1.25".
    """
    return f"${amount:.2f}"


def format_eta(seconds: Optional[float]) -> str:
    """Format ETA seconds into a human-readable string.

    Args:
        seconds: Time in seconds, or None.

    Returns:
        Formatted string like "2m 30s" or "--" if None.
    """
    if seconds is None:
        return "--"

    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining = seconds % 60
        if remaining:
            return f"{minutes}m {remaining}s"
        return f"{minutes}m"
    else:
        hours = seconds // 3600
        remaining = seconds % 3600
        minutes = remaining // 60
        return f"{hours}h {minutes}m"
