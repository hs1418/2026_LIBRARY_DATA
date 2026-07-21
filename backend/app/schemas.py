"""요청/응답 pydantic 모델."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Page(BaseModel):
    no: int
    ko: str
    en: str


# --- Story ---
class StoryCard(BaseModel):
    """서가 목록 카드 — GET /api/stories."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    emoji: str
    keyword: str


class StoryDetail(BaseModel):
    """원작 앞부분·스캔·판권기 — GET /api/stories/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    emoji: str
    keyword: str
    intro_summary: str
    intro_image: str
    bibliography: dict


# --- generate ---
class GenerateRequest(BaseModel):
    lang: Literal["ko", "en"]
    child_speech: str = Field(min_length=1, max_length=2000)


class GenerateResponse(BaseModel):
    session_id: int
    pages: list[Page]
    keywords: list[str]


# --- session ---
class SessionResult(BaseModel):
    """생성 결과·영수증 데이터 — GET /api/sessions/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    story_id: int
    lang: str
    pages: list[Page]
    keywords: list[str]


# --- recommendations ---
class RecommendBook(BaseModel):
    title: str
    author: str = ""
    publisher: str = ""
    call_number: str = ""


class RecommendationsResponse(BaseModel):
    books: list[RecommendBook]
    fallback: bool = False
    # LLM 추천 문구 — 생성 실패 시 null (프론트 계약).
    comment: str | None = None
