"""Custom exception hierarchy for Echo-Bering pipeline."""

from typing import Optional, List


class EchoBeringError(Exception):
    """Base exception for all Echo-Bering errors."""

    pass


class ConfigError(EchoBeringError):
    """Configuration validation error."""

    def __init__(self, message: str, missing_keys: Optional[List[str]] = None):
        self.missing_keys: List[str] = missing_keys or []
        super().__init__(message)


class DependencyError(EchoBeringError):
    """Missing system dependency (e.g., ffmpeg)."""

    def __init__(self, dependency: str, instructions: str):
        self.dependency = dependency
        self.instructions = instructions
        super().__init__(f"Dependency '{dependency}' not found: {instructions}")


class ProviderError(EchoBeringError):
    """Provider API error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class TransientProviderError(ProviderError):
    """Transient error that may succeed on retry."""

    pass


class PermanentProviderError(ProviderError):
    """Permanent error that should not be retried."""

    pass


class BudgetError(EchoBeringError):
    """Budget exceeded error."""

    def __init__(self, current_cost: float, max_budget: float):
        self.current_cost = current_cost
        self.max_budget = max_budget
        super().__init__(f"Budget exceeded: ${current_cost:.2f} > ${max_budget:.2f}")


class CheckpointError(EchoBeringError):
    """Checkpoint read/write error."""

    pass
