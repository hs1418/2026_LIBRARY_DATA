"""감사에서 지적된 미검증 구간 — LLM 재시도·정보나루 성공 경로·lang=en.

전부 mock 경유라 실제 API 키 없이 통과한다.
"""
import json

import httpx
import pytest
from httpx import AsyncClient

from app.models import Story
from app.services import data4library, llm

_VALID_LLM_JSON = json.dumps(
    {
        "pages": [
            {"no": 1, "ko": "두꺼비가 막았어요.", "en": "The toad blocked it."},
            {"no": 2, "ko": "물을 채웠어요.", "en": "Filled with water."},
            {"no": 3, "ko": "잔치에 갔어요.", "en": "Went to the party."},
        ],
        "keywords": ["보은"],
    },
    ensure_ascii=False,
)


# ── LLM 타임아웃·재시도 (ADR-0004: 15초 × 최대 2회) ──────────────────────────
async def test_llm_retries_after_timeout(monkeypatch):
    """1차 호출이 타임아웃돼도 재시도가 성공하면 정상 응답."""
    # 실제 asyncio.wait_for 타임아웃 경로를 타되 테스트는 빨리 끝나게 축소.
    monkeypatch.setattr(llm, "LLM_TIMEOUT", 0.05)
    calls = {"n": 0}

    async def flaky_call_groq(messages: list[dict]) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            import asyncio

            await asyncio.sleep(0.5)  # → asyncio.wait_for 가 TimeoutError 로 자름
        return _VALID_LLM_JSON

    monkeypatch.setattr(llm, "_call_groq", flaky_call_groq)

    pages, keywords = await llm.generate_pages("ko", "두꺼비가 도와줬어요.")
    assert calls["n"] == 2  # 1차 타임아웃 + 재시도 1회
    assert len(pages) == 3
    assert keywords == ["보은"]


async def test_llm_retries_after_parse_error(monkeypatch):
    """1차가 JSON 파싱 실패여도 재시도가 성공하면 정상 응답."""
    calls = {"n": 0}

    async def flaky_call_groq(messages: list[dict]) -> str:
        calls["n"] += 1
        return "죄송합니다, JSON 이 아닙니다" if calls["n"] == 1 else _VALID_LLM_JSON

    monkeypatch.setattr(llm, "_call_groq", flaky_call_groq)

    pages, _ = await llm.generate_pages("ko", "두꺼비가 도와줬어요.")
    assert calls["n"] == 2
    assert len(pages) == 3


async def test_llm_raises_after_all_attempts(monkeypatch):
    """2회 모두 실패하면 LLMError — 시도 횟수는 LLM_MAX_ATTEMPTS 로 상한."""
    calls = {"n": 0}

    async def always_fail(messages: list[dict]) -> str:
        calls["n"] += 1
        raise ValueError("boom")

    monkeypatch.setattr(llm, "_call_groq", always_fail)

    with pytest.raises(llm.LLMError):
        await llm.generate_pages("ko", "두꺼비가 도와줬어요.")
    assert calls["n"] == llm.LLM_MAX_ATTEMPTS


async def test_generate_endpoint_returns_503_when_llm_fails(
    client: AsyncClient, monkeypatch
):
    """재시도까지 실패 → 라우터는 503(세션 종료가 아니라 재입력 유도, ADR-0004 1계층)."""

    async def always_fail(messages: list[dict]) -> str:
        raise ValueError("boom")

    monkeypatch.setattr(llm, "_call_groq", always_fail)

    stories = (await client.get("/api/stories")).json()
    resp = await client.post(
        f"/api/stories/{stories[0]['id']}/generate",
        json={"lang": "ko", "child_speech": "두꺼비가 도와줬어요."},
    )
    assert resp.status_code == 503
    # 내부 예외 문구가 사용자에게 새지 않아야 한다.
    assert "boom" not in resp.text


async def test_generate_endpoint_accepts_lang_en(client: AsyncClient):
    """lang='en' 요청도 200 — 세션에 lang 이 그대로 저장된다."""
    stories = (await client.get("/api/stories")).json()
    resp = await client.post(
        f"/api/stories/{stories[0]['id']}/generate",
        json={"lang": "en", "child_speech": "The toad helped Kongjwi."},
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    result = (await client.get(f"/api/sessions/{session_id}")).json()
    assert result["lang"] == "en"
    assert len(result["pages"]) == 3


# ── 정보나루 성공 경로 (지금까지 폴백 경로만 테스트돼 있었다) ──────────────────
class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


_SRCH_PAYLOAD = {
    "response": {
        "docs": [
            {
                "doc": {
                    # 정보나루 원본 필드명 — 프론트 계약(title/call_number)으로 매핑돼야 한다.
                    "bookname": "개구리 & 두꺼비는 친구",
                    "authors": "아놀드 로벨 글·그림",
                    "publisher": "비룡소",
                    "class_no": "808.8-비46ㅂ-1",
                }
            },
            {"doc": {"bookname": "", "class_no": "813.8-ㄷ"}},  # 제목 없으면 건너뛴다
        ]
    }
}


async def test_data4library_success_maps_fields(monkeypatch):
    """정보나루 200 → bookname→title, class_no→call_number 매핑 + fallback:false."""
    captured = {}

    async def fake_get(self, url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse(_SRCH_PAYLOAD)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(data4library.settings, "data4library_key", "test-key")

    story = Story(
        title="콩쥐팥쥐",
        emoji="🐸",
        keyword="권선징악",
        intro_summary="",
        intro_image="",
        bibliography={},
        fixed_keywords=[],
        recommend_books=[{"title": "시드 폴백", "call_number": "000"}],
    )
    books, fallback = await data4library.search_recommendations(story, ["두꺼비", "보은"])

    assert fallback is False  # 폴백이 아니라 실제 검색 결과
    assert captured["url"] == data4library.SRCH_BOOKS_URL
    assert captured["params"]["keyword"] == "두꺼비"  # 첫 키워드로 검색(AI팀 원본)

    assert len(books) == 1  # 제목 없는 항목은 제외
    book = books[0]
    assert book["title"] == "개구리 & 두꺼비는 친구"  # raw — escape 는 렌더 계층
    assert "&amp;" not in book["title"]
    assert book["author"] == "아놀드 로벨 글·그림"
    assert book["publisher"] == "비룡소"
    assert book["call_number"] == "808.8-비46ㅂ-1"
    assert "class_no" not in book


async def test_data4library_empty_result_falls_back(monkeypatch):
    """200 이지만 결과 0건 → 폴백(시드) + fallback:true."""

    async def fake_get(self, url, params=None, **kwargs):
        return _FakeResponse({"response": {"docs": []}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(data4library.settings, "data4library_key", "test-key")

    story = Story(
        title="콩쥐팥쥐",
        emoji="🐸",
        keyword="권선징악",
        intro_summary="",
        intro_image="",
        bibliography={},
        fixed_keywords=[],
        recommend_books=[{"title": "시드 폴백", "call_number": "000"}],
    )
    books, fallback = await data4library.search_recommendations(story, ["두꺼비"])

    assert fallback is True
    assert books == [
        {
            "title": "시드 폴백",
            "author": "",
            "publisher": "",
            "call_number": "000",
        }
    ]
