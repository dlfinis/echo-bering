"""Logging utilities for Echo-Bering pipeline.

Provides a configured logger with console (INFO) and file (DEBUG) handlers.
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str, output_dir: Path | None = None) -> logging.Logger:
    """Return a configured logger with console INFO and file DEBUG handlers.

    Args:
        name: Logger name (typically __name__).
        output_dir: Directory for log file. Defaults to ./output.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times (idempotent)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Console handler — INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # File handler — DEBUG and above
    log_dir = output_dir or Path("./output")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "echo-bering.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    return logger
