"""요청/응답 pydantic 모델."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Page(BaseModel):
    no: int
    ko: str
    en: str


class IntroPage(BaseModel):
    """북뷰어 한 쪽 — 원작 전문을 그림책처럼 넘겨 보게 하는 단위.

    image/audio 는 파일이 실제로 있을 때만 채워진다. 빈 문자열이면 프론트가 각각
    플레이스홀더 그림 / 글자 수 기반 타이머로 폴백한다.
    """

    no: int
    text: str
    image: str = ""
    audio: str = ""


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
    # 원작 전문이 준비되지 않은 이야기(Story.locked). 프론트가 잠금 카드로 표시한다.
    locked: bool = False


class StoryDetail(BaseModel):
    """원작 앞부분·스캔·판권기 — GET /api/stories/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    emoji: str
    keyword: str
    intro_summary: str
    # 아이에게 던지는 질문(이야기별). 비면 프론트가 기본 문구를 쓴다.
    question: str = ""
    intro_image: str
    # 서가 목록과 같은 값 — 상세만 조회하는 클라이언트도 표지를 알 수 있게 함께 준다.
    cover_image: str = ""
    # 도입부 요약 음성 URL. 빈 문자열이면 프론트가 재생 버튼을 숨긴다.
    # 서가 목록(StoryCard)에는 넣지 않는다 — 상세 화면에서만 재생한다.
    intro_audio: str = ""
    # 북뷰어용 원작 전문. 빈 배열이면 프론트가 intro_summary 카드로 폴백한다.
    # intro_audio 와 같은 이유로 목록(StoryCard)에는 싣지 않는다 — 서가에서는 읽지 않는다.
    intro_pages: list[IntroPage] = []
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
    # booklet: A4 가로 중철 배치(인쇄·제본용, 쪽 순서가 접지 순으로 뒤섞인다)
    # single : A5 세로 1쪽씩 순서대로(태블릿에서 넘겨 보며 그리는 용도)
    layout: Literal["booklet", "single"] = "booklet"


# --- recommendations ---
class RecommendBook(BaseModel):
    title: str
    author: str = ""
    publisher: str = ""
    # 정보나루가 주는 값은 KDC 분류번호(813.5)다. 저자기호까지 붙은 완전한 청구기호는
    # 도서관별 목록 규칙이라 오픈 API 에 없다(srchBooks·srchDtlList·bookExist 모두 확인).
    # 어느 서가인지 알 수 있도록 분류명을 함께 내린다.
    call_number: str = ""
    class_name: str = ""


class RecommendationsResponse(BaseModel):
    books: list[RecommendBook]
    fallback: bool = False
    # LLM 추천 문구 — 생성 실패 시 null (프론트 계약).
    comment: str | None = None
