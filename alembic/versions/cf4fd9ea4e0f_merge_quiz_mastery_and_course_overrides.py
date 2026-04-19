"""merge quiz_mastery and course_overrides

Revision ID: cf4fd9ea4e0f
Revises: 881a62ea5a33, 8a3c1e7b2d10
Create Date: 2026-04-19 02:17:51.922947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf4fd9ea4e0f'
down_revision: Union[str, Sequence[str], None] = ('881a62ea5a33', '8a3c1e7b2d10')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
