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
    # 표지 이미지 URL. 빈 문자열이면 프론트가 이모지 카드로 폴백한다.
    cover_image: str = ""


class StoryDetail(BaseModel):
    """원작 앞부분·스캔·판권기 — GET /api/stories/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    emoji: str
    keyword: str
    intro_summary: str
    intro_image: str
    # 서가 목록과 같은 값 — 상세만 조회하는 클라이언트도 표지를 알 수 있게 함께 준다.
    cover_image: str = ""
    # 도입부 요약 음성 URL. 빈 문자열이면 프론트가 재생 버튼을 숨긴다.
    # 서가 목록(StoryCard)에는 넣지 않는다 — 상세 화면에서만 재생한다.
    intro_audio: str = ""
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


# --- pdf ---
class PdfRequest(BaseModel):
    """PDF 렌더링 요청 — 아이 이름은 쿼리스트링이 아니라 바디로만 받는다.

    URL 에 실리면 액세스 로그·브라우저 히스토리·Referer 에 남기 때문(NFR-6 / ADR-0005).
    """

    author_name: str = Field(default="", max_length=50)


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
