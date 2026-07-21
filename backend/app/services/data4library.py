"""정보나루(도서관 정보나루) 도서 검색 — srchBooks httpx(Async) 호출.

로직 출처: hs1418/2026_LIBRARY_DATA backend/data4library.py — 첫 키워드로 srchBooks 검색,
8초 타임아웃·재시도 0, 실패/빈결과 시 폴백. requests → httpx.AsyncClient 로 포팅(우리 배관).

정책(ADR-0004): 타임아웃 8초, 재시도 0회. 실패 시 즉시 폴백 + 응답에 fallback:true.
폴백 진실 소스는 시드(Story.recommend_books) 한 곳 — 시드가 비었을 때만 모듈 상수(FALLBACK_BOOKS).
보안(ARCHITECTURE §3-3): 이 서비스는 escape 하지 않는다 — llm.py 와 동일 원칙으로
             raw 저장/응답, escape 는 렌더 계층(textContent / Jinja2 autoescape) 한 곳.
             도서 제목에 `&`(예: "개구리 & 두꺼비")가 흔해 저장 시점 escape 는
             영수증 화면에 `&amp;` 리터럴을 그대로 노출시킨다.
"""
import logging

import httpx

from app.config import settings
from app.models import Story

logger = logging.getLogger(__name__)

DATA4LIBRARY_TIMEOUT = 8.0
SRCH_BOOKS_URL = "https://data4library.kr/api/srchBooks"

# 정보나루 API 실패 & 시드도 비었을 때 쓰는 최후 폴백 5권 (NFR-3, ADR-0004).
# 데이터 출처: AI팀 원본 FALLBACK_BOOKS(정보나루 대출 데이터 큐레이션).
# 원본 필드명 call_no → 프론트 계약대로 call_number 로 통일.
FALLBACK_BOOKS = [
    {
        "title": "콩쥐팥쥐",
        "author": "이성실 글 ; 박완서 그림",
        "publisher": "보림",
        "call_number": "813.8-보64ㅋ-2",
    },
    {
        "title": "화요일의 두꺼비",
        "author": "러셀 에릭슨 지음 ; 햇살과나무꾼 옮김",
        "publisher": "사계절",
        "call_number": "843-에296ㅎ",
    },
    {
        "title": "개구리와 두꺼비는 친구",
        "author": "아놀드 로벨 글·그림 ; 엄혜숙 옮김",
        "publisher": "비룡소",
        "call_number": "808.8-비46ㅂ-1",
    },
    {
        "title": "신데렐라 (세계 전래동화)",
        "author": "샤를 페로 원작 ; 이경혜 글",
        "publisher": "시공주니어",
        "call_number": "808.8-시16ㅅ-12",
    },
    {
        "title": "혹부리 영감과 은혜 갚은 두꺼비",
        "author": "서정오 글 ; 한병호 그림",
        "publisher": "보리",
        "call_number": "813.8-보94ㅎ",
    },
]


def _normalize_book(item: dict) -> dict:
    """폴백 도서 dict(시드 or 모듈 상수)를 응답 스키마로 정규화(raw — escape 안 함)."""
    return {
        "title": str(item.get("title", "")),
        "author": str(item.get("author", "")),
        "publisher": str(item.get("publisher", "")),
        "call_number": str(item.get("call_number", "")),
    }


def _fallback_books(story: Story) -> list[dict]:
    """폴백 도서 목록 — 시드(Story.recommend_books) 우선, 비었을 때만 모듈 상수."""
    seed = [item for item in (story.recommend_books or []) if isinstance(item, dict)]
    source = seed if seed else FALLBACK_BOOKS
    return [_normalize_book(item) for item in source]


async def _srch_books(query: str) -> list[dict]:
    """정보나루 srchBooks 호출 — 네트워크 seam(테스트는 이 함수를 monkeypatch 한다).

    반환: [{title, author, publisher, call_number}] (raw 텍스트 — escape 는 렌더 계층).
    실패 시 예외 전파.
    필드 매핑: 정보나루 bookname → title, authors → author, class_no → call_number.
    """
    async with httpx.AsyncClient(timeout=DATA4LIBRARY_TIMEOUT) as client:
        resp = await client.get(
            SRCH_BOOKS_URL,
            params={
                "authKey": settings.data4library_key,
                "keyword": query,
                "pageNo": 1,
                "pageSize": 5,
                "format": "json",
            },
        )
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])

    books: list[dict] = []
    for entry in docs:
        book = entry.get("doc", entry)
        title = book.get("bookname", "")
        if not title:
            continue
        books.append(
            {
                "title": str(title),
                "author": str(book.get("authors", "")),
                "publisher": str(book.get("publisher", "")),
                "call_number": str(book.get("class_no", "")),
            }
        )
    return books


async def search_recommendations(
    story: Story, keywords: list[str]
) -> tuple[list[dict], bool]:
    """키워드 → 정보나루 검색. 반환: (books, fallback).

    AI팀 원본대로 첫 키워드를 검색어로 사용. 실패(타임아웃·HTTP 오류·빈 결과) 시
    즉시 (폴백 도서, True). fallback 판정은 서비스가 정보나루 성공 여부로 직접 내린다.
    """
    query = (keywords[0] if keywords else "").strip()
    if not query or not settings.data4library_key:
        return _fallback_books(story), True

    try:
        books = await _srch_books(query)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("정보나루 API 호출 실패, 폴백 데이터로 대체: %s", exc)
        return _fallback_books(story), True

    if not books:
        return _fallback_books(story), True
    return books, False
