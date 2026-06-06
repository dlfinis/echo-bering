"""Fixtures for processor tests."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_run_for_chunking():
    """Mock subprocess.run for chunking tests."""
    with patch("src.processors.chunking.subprocess.run") as mock:
        mock.return_value = MagicMock(returncode=0, stderr="")
        yield mock
