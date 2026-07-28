"""데이터 모델 — Story(정적 시딩), Session(런타임).

JSON 컬럼은 sa.JSON 만 사용(postgresql.JSONB 금지) — 테스트를 SQLite 로 돌리기 위한 이식성.
아이 이름 컬럼은 어느 테이블에도 두지 않는다(ADR-0005 / NFR-6): PDF 렌더링 파라미터로만 전달.
"""
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    emoji: Mapped[str] = mapped_column(sa.String(16), default="", nullable=False)
    keyword: Mapped[str] = mapped_column(sa.String(100), default="", nullable=False)
    intro_summary: Mapped[str] = mapped_column(sa.Text, default="", nullable=False)
    intro_image: Mapped[str] = mapped_column(sa.String(500), default="", nullable=False)
    # 도입부 요약 음성(/static/audio/{slug}.mp3). 개발 시점에 edge-tts 로 미리 만들어
    # 커밋하는 정적 자산이라 런타임 TTS 호출은 없다(ADR-0004 — 현장 인터넷/외부 API 가
    # 재생 실패 지점이 되면 안 된다). 비어 있으면 프론트가 재생 버튼째 숨긴다.
    intro_audio: Mapped[str] = mapped_column(sa.String(500), default="", nullable=False)
    # 북뷰어용 원작 전문 페이지 [{no, text, image, audio}] — 시드의 INTRO_PAGE_n 에서 채운다.
    # 페이지가 없는 이야기는 빈 배열이고, 프론트는 intro_summary 카드로 폴백한다.
    # image/audio 는 파일이 실제로 있을 때만 경로가 들어간다(표지·음성과 같은 폴백 규칙).
    intro_pages: Mapped[list] = mapped_column(sa.JSON, default=list, nullable=False)
    # 디자인팀 표지 이미지(/static/covers/{slug}.jpg). 비어 있으면 이모지 표지로 폴백한다
    # — 파일이 유실돼도 서가·PDF 가 깨지지 않게 하는 안전망.
    cover_image: Mapped[str] = mapped_column(sa.String(500), default="", nullable=False)
    # 서지(판권기) / 폴백 키워드 / 폴백 추천도서 — 전부 시딩 시점에 채워지는 정적 데이터
    bibliography: Mapped[dict] = mapped_column(sa.JSON, default=dict, nullable=False)
    fixed_keywords: Mapped[list] = mapped_column(sa.JSON, default=list, nullable=False)
    recommend_books: Mapped[list] = mapped_column(sa.JSON, default=list, nullable=False)

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="story", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    story_id: Mapped[int] = mapped_column(
        sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    lang: Mapped[str] = mapped_column(sa.String(2), default="ko", nullable=False)
    child_speech: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # 페이지 분할 결과 [{no, ko, en}] — LLM 이 분할해 반환(ADR-0005)
    pages: Mapped[list] = mapped_column(sa.JSON, default=list, nullable=False)
    keywords: Mapped[list] = mapped_column(sa.JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    story: Mapped["Story"] = relationship(back_populates="sessions")
