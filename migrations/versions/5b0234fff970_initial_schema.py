"""initial_schema

Revision ID: 5b0234fff970
Revises: 
Create Date: 2026-06-18 16:01:21.564826

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '5b0234fff970'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
