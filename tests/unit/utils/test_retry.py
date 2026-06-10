"""Tests for RetryPolicy in src.utils.retry."""

import asyncio

import pytest

from src.utils.errors import (
    ProviderError,
    TransientProviderError,
    PermanentProviderError,
)
from src.utils.retry import RetryPolicy


class TestRetryPolicy:
    """Test RetryPolicy async decorator with exponential backoff."""

    @pytest.mark.asyncio
    async def test_transient_error_retries_and_succeeds(self):
        """Transient errors trigger retries until success."""
        call_count = 0

        class DummyClient:
            async def flaky_method(self):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise TransientProviderError("rate limited", status_code=429)
                return "success"

        client = DummyClient()
        policy = RetryPolicy(max_retries=3, base_delay=0.01, max_delay=0.1)
        result = await policy.retry(client.flaky_method)()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_error_raises_immediately(self):
        """Permanent errors are not retried."""
        call_count = 0

        async def doomed():
            nonlocal call_count
            call_count += 1
            raise PermanentProviderError("invalid model")

        policy = RetryPolicy(max_retries=3, base_delay=0.01)
        with pytest.raises(PermanentProviderError):
            await policy.retry(doomed)()
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises(self):
        """After max_retries, TransientProviderError propagates."""
        async def always_fails():
            raise TransientProviderError("persistent failure", status_code=500)

        policy = RetryPolicy(max_retries=2, base_delay=0.01, max_delay=0.1)
        with pytest.raises(TransientProviderError):
            await policy.retry(always_fails)()

    @pytest.mark.asyncio
    async def test_on_backoff_callback_fires(self):
        """on_backoff callback is called on each retry."""
        callback_calls = []

        def on_backoff(details):
            callback_calls.append(details["tries"])

        call_count = 0

        async def retry_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TransientProviderError("try again")
            return "done"

        policy = RetryPolicy(max_retries=3, base_delay=0.01, max_delay=0.1, on_backoff=on_backoff)
        result = await policy.retry(retry_twice)()
        assert result == "done"
        assert len(callback_calls) > 0

    @pytest.mark.asyncio
    async def test_non_provider_error_passes_through(self):
        """Non-ProviderError exceptions are not caught by retry."""
        async def raises_value_error():
            raise ValueError("unexpected")

        policy = RetryPolicy(max_retries=2, base_delay=0.01)
        with pytest.raises(ValueError):
            await policy.retry(raises_value_error)()

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """Successful call returns immediately without retries."""
        call_count = 0

        async def immediate():
            nonlocal call_count
            call_count += 1
            return 42

        policy = RetryPolicy(max_retries=3, base_delay=0.01)
        result = await policy.retry(immediate)()
        assert result == 42
        assert call_count == 1
