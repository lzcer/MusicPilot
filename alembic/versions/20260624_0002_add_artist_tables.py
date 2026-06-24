"""Add artist and artist_aliases tables.

Revision ID: 20260624_0002
Revises: 20260614_0001
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260624_0002"
down_revision: str | None = "20260614_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("normalized_name", sa.String(length=512), nullable=False),
        sa.Column("external_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_artists_normalized_name"),
        "artists",
        ["normalized_name"],
        unique=False,
    )
    op.create_table(
        "artist_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("artist_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_artist_aliases_artist_id"),
        "artist_aliases",
        ["artist_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_artist_aliases_alias"),
        "artist_aliases",
        ["alias"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_artist_aliases_alias"), table_name="artist_aliases")
    op.drop_index(op.f("ix_artist_aliases_artist_id"), table_name="artist_aliases")
    op.drop_table("artist_aliases")
    op.drop_index(op.f("ix_artists_normalized_name"), table_name="artists")
    op.drop_table("artists")