"""add_code_data_flags

Revision ID: 1eaac4569706
Revises: 5b0234fff970
Create Date: 2026-06-18 16:29:41.632612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1eaac4569706'
down_revision: Union[str, Sequence[str], None] = '5b0234fff970'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("papers", sa.Column("has_code", sa.Integer(), server_default="0", nullable=False))
    op.add_column("papers", sa.Column("has_data", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("papers") as batch_op:
        batch_op.drop_column("has_code")
        batch_op.drop_column("has_data")
