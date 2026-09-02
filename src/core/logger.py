"""Structured logging setup using structlog."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def setup_logging(
    level: str = "INFO",
    log_format: str = "json",
    log_file: str | None = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: "json" for production, "console" for development
        log_file: Optional file path for log output
    """

    # Configure standard library logging
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        stream=sys.stdout,
    )

    # Shared processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        # Production: JSON output
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Development: colored console output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Add file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)

        if log_format == "json":
            formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
                foreign_pre_chain=shared_processors,
            )
        else:
            formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.dev.ConsoleRenderer(colors=False),
                foreign_pre_chain=shared_processors,
            )

        file_handler.setFormatter(formatter)
        logging.root.addHandler(file_handler)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a named logger instance."""
    return structlog.get_logger(name)
