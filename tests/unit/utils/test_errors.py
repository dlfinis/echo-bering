"""Tests for exception hierarchy in src.utils.errors."""

import pytest
from src.utils.errors import (
    EchoBeringError,
    ConfigError,
    DependencyError,
    ProviderError,
    TransientProviderError,
    PermanentProviderError,
    BudgetError,
    CheckpointError,
)


class TestExceptionInheritance:
    """Verify all exceptions inherit from EchoBeringError."""

    def test_config_error_is_echo_bering_error(self):
        assert issubclass(ConfigError, EchoBeringError)

    def test_dependency_error_is_echo_bering_error(self):
        assert issubclass(DependencyError, EchoBeringError)

    def test_provider_error_is_echo_bering_error(self):
        assert issubclass(ProviderError, EchoBeringError)

    def test_transient_provider_error_is_provider_error(self):
        assert issubclass(TransientProviderError, ProviderError)

    def test_permanent_provider_error_is_provider_error(self):
        assert issubclass(PermanentProviderError, ProviderError)

    def test_budget_error_is_echo_bering_error(self):
        assert issubclass(BudgetError, EchoBeringError)

    def test_checkpoint_error_is_echo_bering_error(self):
        assert issubclass(CheckpointError, EchoBeringError)


class TestConfigError:
    """Test ConfigError instantiation and attributes."""

    def test_config_error_with_message(self):
        err = ConfigError("missing key: api_key")
        assert str(err) == "missing key: api_key"
        assert err.missing_keys == []

    def test_config_error_with_missing_keys(self):
        err = ConfigError("multiple missing", missing_keys=["GROQ_API_KEY", "INPUT_VIDEO"])
        assert "multiple missing" in str(err)
        assert err.missing_keys == ["GROQ_API_KEY", "INPUT_VIDEO"]


class TestDependencyError:
    """Test DependencyError with dependency name and instructions."""

    def test_dependency_error_message_format(self):
        err = DependencyError("ffmpeg", "install via: brew install ffmpeg")
        assert "ffmpeg" in str(err)
        assert "install via: brew install ffmpeg" in str(err)

    def test_dependency_error_attributes(self):
        err = DependencyError("ffprobe", "install via: brew install ffmpeg")
        assert err.dependency == "ffprobe"
        assert err.instructions == "install via: brew install ffmpeg"


class TestProviderError:
    """Test ProviderError with optional status code."""

    def test_provider_error_message_only(self):
        err = ProviderError("API rate limited")
        assert str(err) == "API rate limited"
        assert err.status_code is None

    def test_provider_error_with_status_code(self):
        err = ProviderError("server error", status_code=503)
        assert str(err) == "server error"
        assert err.status_code == 503


class TestTransientProviderError:
    """Test TransientProviderError inherits ProviderError behavior."""

    def test_transient_error_message_and_status(self):
        err = TransientProviderError("timeout", status_code=429)
        assert str(err) == "timeout"
        assert err.status_code == 429

    def test_transient_is_catchable_as_provider_error(self):
        with pytest.raises(ProviderError):
            raise TransientProviderError("retry later")


class TestPermanentProviderError:
    """Test PermanentProviderError inherits ProviderError behavior."""

    def test_permanent_error_message(self):
        err = PermanentProviderError("invalid model")
        assert str(err) == "invalid model"

    def test_permanent_is_catchable_as_provider_error(self):
        with pytest.raises(ProviderError):
            raise PermanentProviderError("model not found")


class TestBudgetError:
    """Test BudgetError with cost tracking."""

    def test_budget_error_format(self):
        err = BudgetError(current_cost=5.50, max_budget=2.0)
        assert "5.50" in str(err)
        assert "2.00" in str(err)

    def test_budget_error_attributes(self):
        err = BudgetError(current_cost=3.25, max_budget=1.0)
        assert err.current_cost == 3.25
        assert err.max_budget == 1.0


class TestCheckpointError:
    """Test CheckpointError simple instantiation."""

    def test_checkpoint_error_message(self):
        err = CheckpointError("failed to read stage data")
        assert str(err) == "failed to read stage data"
