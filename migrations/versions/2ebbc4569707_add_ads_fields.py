"""add_ads_fields

Revision ID: 2ebbc4569707
Revises: 1eaac4569706
Create Date: 2026-06-23 11:22:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ebbc4569707'
down_revision: Union[str, Sequence[str], None] = '1eaac4569706'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("papers", sa.Column("bibcode", sa.String(), nullable=True))
    op.add_column("papers", sa.Column("read_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("papers", sa.Column("refereed", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("papers") as batch_op:
        batch_op.drop_column("bibcode")
        batch_op.drop_column("read_count")
        batch_op.drop_column("refereed")
