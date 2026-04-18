"""Tenacity-based retry decorators for external system calls."""

from __future__ import annotations

from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.exceptions import TUMSystemUnavailableError


def retry_external(
    *,
    max_attempts: int = 3,
    min_wait: float = 0.5,
    max_wait: float = 10.0,
) -> Any:
    """Retry decorator for external TUM system calls with exponential backoff + jitter."""
    return retry(
        retry=retry_if_exception_type((TUMSystemUnavailableError, ConnectionError, TimeoutError)),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=min_wait, max=max_wait),
        reraise=True,
    )
