"""Tests for logger configuration in src.utils.logger."""

import logging
import pytest
from src.utils.logger import get_logger


class TestGetLogger:
    """Test get_logger returns properly configured logger."""

    def test_get_logger_returns_logger(self):
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_logger_has_correct_name(self):
        logger = get_logger("my_custom_name")
        assert logger.name == "my_custom_name"

    def test_logger_has_console_handler(self):
        logger = get_logger("console_test")
        handlers = logger.handlers
        console_handlers = [h for h in handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert len(console_handlers) >= 1

    def test_console_handler_level_is_info(self):
        logger = get_logger("level_test")
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                assert handler.level == logging.INFO

    def test_logger_does_not_propagate(self):
        logger = get_logger("no_propagate_test")
        assert logger.propagate is False

    def test_get_logger_is_idempotent(self):
        """Calling get_logger twice with same name returns same instance."""
        logger1 = get_logger("idempotent_test")
        logger2 = get_logger("idempotent_test")
        assert logger1 is logger2
        # Handlers should not be duplicated
        assert len(logger1.handlers) <= 2
