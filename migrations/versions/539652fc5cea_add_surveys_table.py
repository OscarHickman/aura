"""add_surveys_table

Revision ID: 539652fc5cea
Revises: 2ebbc4569707
Create Date: 2026-06-24 00:08:56.526736

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '539652fc5cea'
down_revision: Union[str, Sequence[str], None] = '2ebbc4569707'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "surveys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), unique=True, nullable=False),
        sa.Column("keywords", sa.String(), nullable=False),
    )
    op.create_index("idx_surveys_name", "surveys", ["name"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_surveys_name", table_name="surveys")
    op.drop_table("surveys")
