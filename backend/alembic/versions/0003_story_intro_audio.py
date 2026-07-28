"""story intro_audio — 도입부 요약 음성(mp3) 경로

Revision ID: 0003_story_intro_audio
Revises: 0002_story_cover_image
Create Date: 2026-07-28
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_story_intro_audio"
down_revision: str | None = "0002_story_cover_image"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # cover_image(0002)와 같은 이유로 server_default="" 를 남긴다 — 기존 행에 NOT NULL 을
    # 걸 수 있고, SQLite 는 ALTER COLUMN ... DROP DEFAULT 를 지원하지 않아 떼면 로컬
    # 마이그레이션이 깨진다. 모델 쪽 default="" 와 의미가 같아 부작용도 없다.
    op.add_column(
        "stories",
        sa.Column("intro_audio", sa.String(length=500), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("stories", "intro_audio")
