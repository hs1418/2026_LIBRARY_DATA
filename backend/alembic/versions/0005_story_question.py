"""story question — 아이에게 던지는 이야기별 질문

Revision ID: 0005_story_question
Revises: 0004_story_intro_pages
Create Date: 2026-07-28
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_story_question"
down_revision: str | None = "0004_story_intro_pages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0002~0004 와 같은 이유로 server_default 를 남긴다 — 기존 행에 NOT NULL 을 걸 수 있고,
    # SQLite 는 ALTER COLUMN ... DROP DEFAULT 를 지원하지 않는다.
    op.add_column(
        "stories",
        sa.Column("question", sa.String(200), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("stories", "question")
