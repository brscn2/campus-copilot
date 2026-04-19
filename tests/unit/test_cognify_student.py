"""Unit tests for trigger_student_cognify."""

from __future__ import annotations

import pytest

from src.lib.cognify import trigger_student_cognify


@pytest.mark.asyncio
async def test_trigger_student_cognify_is_noop() -> None:
    """trigger_student_cognify is a no-op (improve endpoint not available on Cognee Cloud)."""
    await trigger_student_cognify("stu-42")
