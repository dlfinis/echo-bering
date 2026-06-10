"""Retry policy with exponential backoff and jitter for transient provider errors.

Uses the `backoff` library for robust retry handling.
"""

import asyncio
from functools import wraps
from typing import Callable, Optional

import backoff

from src.utils.errors import TransientProviderError, PermanentProviderError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RetryPolicy:
    """Retry policy with exponential backoff and optional on_backoff callback."""

    def __init__(
        self,
        max_retries: int = 2,
        base_delay: float = 1.0,
        max_delay: float = 10.0,
        on_backoff: Optional[Callable] = None,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._on_backoff = on_backoff

    def retry(self, func: Callable) -> Callable:
        """Decorator to add retry logic with exponential backoff.

        Only retries on `TransientProviderError`. Permanent and other errors
        pass through immediately.

        Args:
            func: Async function to wrap.

        Returns:
            Wrapped async function with retry behavior.
        """

        def _on_backoff_handler(details):
            """Internal backoff handler that logs and calls user callback."""
            logger.warning(
                "Retry %d/%d for %s after %.2fs",
                details["tries"],
                self.max_retries + 1,
                details["target"].__name__,
                details["wait"],
            )
            if self._on_backoff:
                self._on_backoff(details)

        @backoff.on_exception(
            backoff.expo,
            TransientProviderError,
            max_tries=self.max_retries + 1,
            max_value=self.max_delay,
            on_backoff=_on_backoff_handler,
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper
