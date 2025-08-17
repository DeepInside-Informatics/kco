"""Logging configuration and utilities."""

import logging
import sys

import structlog
from structlog.stdlib import LoggerFactory


def setup_logging(log_level: str = "INFO") -> structlog.BoundLogger:
    """Setup structured logging with structlog and stdlib logging."""

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.dev.ConsoleRenderer() if log_level == "DEBUG" else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger("kco.operator")
