"""Unit tests for the Academic agent's thesis-related tools."""

from __future__ import annotations

import pytest

from src.agents.academic.tools import draft_thesis_email


@pytest.mark.asyncio
async def test_draft_thesis_email_returns_draft() -> None:
    result = await draft_thesis_email.ainvoke(
        {
            "student_name": "Max Mustermann",
            "student_program": "Informatics, M.Sc.",
            "professor_name": "Prof. Dr. Alice Example",
            "professor_email": "alice@tum.de",
            "thesis_topic": "Cool ML Topic",
            "motivation": "I have experience in ML and find this topic fascinating.",
        }
    )
    assert result["status"] == "draft"
    assert result["to"] == "alice@tum.de"
    assert "Cool ML Topic" in result["subject"]
    assert "Max Mustermann" in result["body"]
    assert "Informatics, M.Sc." in result["body"]
