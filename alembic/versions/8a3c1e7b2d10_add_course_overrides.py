"""add course_overrides JSONB to students

Revision ID: 8a3c1e7b2d10
Revises: 09940950771b
Create Date: 2026-04-18 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8a3c1e7b2d10"
down_revision: str | Sequence[str] | None = "09940950771b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add course_overrides JSONB column to students."""
    op.add_column(
        "students",
        sa.Column(
            "course_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    """Drop course_overrides column."""
    op.drop_column("students", "course_overrides")
