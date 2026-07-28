"""story intro_pages — 북뷰어용 원작 전문 페이지 [{no, text, image, audio}]

Revision ID: 0004_story_intro_pages
Revises: 0003_story_intro_audio
Create Date: 2026-07-28
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_story_intro_pages"
down_revision: str | None = "0003_story_intro_audio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0002/0003 과 같은 이유로 server_default 를 남긴다 — 기존 행에 NOT NULL 을 걸 수 있고,
    # SQLite 는 ALTER COLUMN ... DROP DEFAULT 를 지원하지 않아 떼면 로컬 마이그레이션이
    # 깨진다. JSON 컬럼이라 기본값은 빈 배열 리터럴이고, 모델 쪽 default=list 와 같은 뜻이다.
    op.add_column(
        "stories",
        sa.Column("intro_pages", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("stories", "intro_pages")
