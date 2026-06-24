"""add_source_to_tags

Revision ID: 6790c6856d7d
Revises: 539652fc5cea
Create Date: 2026-06-24 00:17:12.489927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6790c6856d7d'
down_revision: Union[str, Sequence[str], None] = '539652fc5cea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("tags", sa.Column("source", sa.String(), server_default="user", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tags") as batch_op:
        batch_op.drop_column("source")
