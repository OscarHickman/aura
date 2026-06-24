"""add_repo_metadata

Revision ID: cf9a50ecd92a
Revises: 6bd1b5d8ad14
Create Date: 2026-06-24 08:16:35.377106

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf9a50ecd92a'
down_revision: Union[str, Sequence[str], None] = '6bd1b5d8ad14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "repo_metadata",
        sa.Column("arxiv_id", sa.String(), primary_key=True),
        sa.Column("repo_url", sa.String(), nullable=False),
        sa.Column("stars", sa.Integer(), server_default="0", nullable=True),
        sa.Column("last_commit", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("fetched_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["arxiv_id"], ["papers.arxiv_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("repo_metadata")
