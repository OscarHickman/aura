"""Deduplicate notes replayed by mobile clients.

Revision ID: d813f210abcd
Revises: cf9a50ecd92a
"""
from alembic import op
import sqlalchemy as sa

revision = "d813f210abcd"
down_revision = "cf9a50ecd92a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "client_mutation_id" not in {column["name"] for column in inspector.get_columns("notes")}:
        op.add_column("notes", sa.Column("client_mutation_id", sa.Text(), nullable=True))
    if "idx_notes_client_mutation" not in {index["name"] for index in inspector.get_indexes("notes")}:
        op.create_index("idx_notes_client_mutation", "notes", ["user_id", "client_mutation_id"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_notes_client_mutation", table_name="notes")
    op.drop_column("notes", "client_mutation_id")
