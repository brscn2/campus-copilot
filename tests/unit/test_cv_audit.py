"""Unit tests for the Career agent's CV audit tool."""

from __future__ import annotations

import pytest

from src.agents.career.tools import audit_cv


@pytest.mark.asyncio
async def test_audit_cv_full_cv() -> None:
    result = await audit_cv.ainvoke(
        {
            "sections_present": [
                "education",
                "experience",
                "skills",
                "projects",
                "languages",
                "certifications",
            ],
            "target_role": "working_student",
        }
    )
    assert result["completeness_score"] == 100
    assert result["sections_missing"] == []


@pytest.mark.asyncio
async def test_audit_cv_partial_cv() -> None:
    result = await audit_cv.ainvoke(
        {
            "sections_present": ["education", "skills"],
            "target_role": "working_student",
        }
    )
    assert result["completeness_score"] < 100
    assert "projects" in result["sections_missing"]
    assert len(result["tips"]) > 0


@pytest.mark.asyncio
async def test_audit_cv_new_grad_tips() -> None:
    result = await audit_cv.ainvoke(
        {
            "sections_present": ["education", "experience", "skills", "projects"],
            "target_role": "new_grad",
        }
    )
    assert any("certifications" in tip.lower() for tip in result["tips"])


@pytest.mark.asyncio
async def test_audit_cv_empty_cv() -> None:
    result = await audit_cv.ainvoke(
        {
            "sections_present": [],
            "target_role": "internship",
        }
    )
    assert result["completeness_score"] == 0
    assert len(result["sections_missing"]) == 6
