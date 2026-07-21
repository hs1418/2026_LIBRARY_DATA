"""initial — stories, sessions

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.Column("intro_summary", sa.Text(), nullable=False),
        sa.Column("intro_image", sa.String(length=500), nullable=False),
        sa.Column("bibliography", sa.JSON(), nullable=False),
        sa.Column("fixed_keywords", sa.JSON(), nullable=False),
        sa.Column("recommend_books", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column("child_speech", sa.Text(), nullable=False),
        sa.Column("pages", sa.JSON(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("stories")
