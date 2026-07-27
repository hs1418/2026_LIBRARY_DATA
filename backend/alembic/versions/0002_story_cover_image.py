"""story cover_image — 디자인팀 표지 이미지 경로

Revision ID: 0002_story_cover_image
Revises: 0001_initial
Create Date: 2026-07-27
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_story_cover_image"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 행에도 NOT NULL 을 걸 수 있게 server_default 로 빈 문자열을 채운다.
    # 이 default 는 뒤에서 떼지 않는다 — SQLite 는 ALTER COLUMN ... DROP DEFAULT 를
    # 지원하지 않아 마이그레이션이 로컬(SQLite)에서 깨지고, 빈 문자열 default 는
    # 모델 쪽 default="" 와 의미가 같아 남겨도 부작용이 없다.
    op.add_column(
        "stories",
        sa.Column("cover_image", sa.String(length=500), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("stories", "cover_image")
