"""add_tracked_authors

Revision ID: 6bd1b5d8ad14
Revises: 6790c6856d7d
Create Date: 2026-06-24 07:48:59.958266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6bd1b5d8ad14'
down_revision: Union[str, Sequence[str], None] = '6790c6856d7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tracked_authors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("orcid", sa.String(), nullable=True),
        sa.Column("affiliation", sa.String(), nullable=True),
        sa.Column("relationship", sa.String(), nullable=False),
        sa.UniqueConstraint("name", "relationship", name="uq_tracked_authors_name_relationship"),
    )
    op.create_index("idx_tracked_authors_name", "tracked_authors", ["name"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_tracked_authors_name", table_name="tracked_authors")
    op.drop_table("tracked_authors")
