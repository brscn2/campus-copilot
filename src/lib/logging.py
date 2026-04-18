"""Structured logging setup with PII redaction."""

from __future__ import annotations

from typing import Any

import structlog

REDACTED_KEYS = frozenset(
    {
        "api_key",
        "token",
        "authorization",
        "password",
        "secret",
        "credential",
        "google_calendar_token",
        "tum_credentials",
        "aws_secret_access_key",
    }
)


def _redact_sensitive_values(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace values of known-sensitive keys with '[REDACTED]'."""
    for key in event_dict:
        if key.lower() in REDACTED_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def setup_logging(*, json_output: bool = False) -> None:
    """Configure structlog for the application."""
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _redact_sensitive_values,  # type: ignore[list-item]
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger instance."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
