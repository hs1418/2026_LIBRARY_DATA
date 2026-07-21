"""정보나루(도서관 정보나루) 도서 검색 — srchBooks httpx 호출.

정책(ADR-0004): 타임아웃 8초, 재시도 0회. 실패 시 즉시 Story.recommend_books 폴백 +
응답에 fallback:true. 정부기관 API 는 지연 시 재시도해도 개선 안 될 가능성이 높아 즉시 폴백.
추천 문구(blurb)는 llm.make_recommendation_blurb 로 2차 생성(실패 시 문구 없이 목록만).
"""
import html

import httpx

from app.config import settings
from app.models import Story

DATA4LIBRARY_TIMEOUT = 8.0
SRCH_BOOKS_URL = "https://data4library.kr/api/srchBooks"


def _fallback_books(story: Story) -> list[dict]:
    """Story 의 고정 추천도서(폴백)를 응답 스키마 형태로 정규화."""
    books: list[dict] = []
    for item in story.recommend_books or []:
        if isinstance(item, dict):
            books.append(
                {
                    "title": html.escape(str(item.get("title", ""))),
                    "call_number": html.escape(str(item.get("call_number", ""))),
                }
            )
    return books


async def _srch_books(query: str) -> list[dict]:
    """정보나루 srchBooks 호출 — 네트워크 seam(테스트는 이 함수를 monkeypatch 한다).

    반환: [{title, call_number}] (이미 html.escape 적용). 실패 시 예외 전파.
    """
    async with httpx.AsyncClient(timeout=DATA4LIBRARY_TIMEOUT) as client:
        resp = await client.get(
            SRCH_BOOKS_URL,
            params={
                "authKey": settings.data4library_key,
                "keyword": query,
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
                "title": html.escape(str(title)),
                "call_number": html.escape(str(book.get("class_no", ""))),
            }
        )
    return books


async def search_recommendations(
    story: Story, keywords: list[str]
) -> tuple[list[dict], bool]:
    """키워드 → 정보나루 검색. 반환: (books, fallback).

    실패(타임아웃·HTTP 오류·빈 결과)하면 (Story.recommend_books, True).
    """
    query = " ".join(keywords[:2]).strip() or (keywords[0] if keywords else "")
    if not query:
        return _fallback_books(story), True

    try:
        books = await _srch_books(query)
    except (httpx.HTTPError, ValueError, KeyError):
        return _fallback_books(story), True

    if not books:
        return _fallback_books(story), True
    return books, False
