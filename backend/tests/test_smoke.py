"""골든 패스 스모크 테스트 — SQLite(aiosqlite) 인메모리 + LLM/정보나루 mock.

검증:
① 시드 후 GET /api/stories 200
② POST generate → session 생성·pages 3개·저장은 raw 텍스트(escape 는 렌더 계층 책임, A-1)
③ GET /api/sessions/{id} 200
④ recommendations 폴백 경로(정보나루 실패 시 fallback:true)
⑤ POST /pdf — 이름은 바디로만 받고 렌더링에만 쓰이며 sessions 행에 저장되지 않음(NFR-6)
⑥ GET /pdf 는 demo 폴백 전용
실제 Playwright 렌더링은 @pytest.mark.pdf 로 분리 — 서비스 함수를 직접 1회 호출해 바이트 > 0 확인.
"""
import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from app.db import get_session
from app.main import app
from app.models import Session as StorySession
from app.models import Story
from app.services import pdf as pdf_service
from tests.conftest import AUTHOR_NAME, INJECTED_SPEECH


async def test_golden_path(client: AsyncClient):
    # ① 서가 목록
    resp = await client.get("/api/stories")
    assert resp.status_code == 200
    stories = resp.json()
    assert len(stories) == 1
    story_id = stories[0]["id"]
    assert stories[0]["title"] == "콩쥐팥쥐"

    # ② generate — pages 3개 + XSS 이스케이프
    resp = await client.post(
        f"/api/stories/{story_id}/generate",
        json={"lang": "ko", "child_speech": INJECTED_SPEECH},
    )
    assert resp.status_code == 200
    body = resp.json()
    session_id = body["session_id"]
    assert len(body["pages"]) == 3
    assert len(body["keywords"]) == 3
    page1_ko = body["pages"][0]["ko"]
    # 저장·API 응답은 raw 텍스트다(A-1). escape 는 렌더 계층에서만 한다 —
    # 여기서 escape 하면 Jinja2 autoescape/textContent 와 겹쳐 이중 이스케이프가 된다.
    # 실제 XSS 차단은 렌더 결과로 검증한다 → test_escape_render.py
    assert page1_ko == INJECTED_SPEECH
    assert "&lt;" not in page1_ko
    assert "&amp;" not in page1_ko

    # ③ 세션 결과 조회
    resp = await client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    result = resp.json()
    assert result["id"] == session_id
    assert len(result["pages"]) == 3

    # ④ 추천 폴백 경로 — 정보나루 실패 → fallback:true + Story.recommend_books
    resp = await client.get(f"/api/sessions/{session_id}/recommendations")
    assert resp.status_code == 200
    recs = resp.json()
    assert recs["fallback"] is True
    assert len(recs["books"]) == 2
    assert recs["books"][0]["title"] == "은혜 갚은 두꺼비"
    # 필드명 계약: call_number 사용, AI팀 원본 call_no 는 응답에 없어야 함.
    assert recs["books"][0]["call_number"] == "813.8-ㄷ"
    assert "call_no" not in recs["books"][0]
    # comment 는 생성 주체가 없어 null 고정(프론트 계약).
    assert "comment" in recs
    assert recs["comment"] is None


async def test_story_not_found(client: AsyncClient):
    resp = await client.get("/api/stories/9999")
    assert resp.status_code == 404


async def test_pdf_post_renders_and_never_persists_author_name(client: AsyncClient, monkeypatch):
    """아이 이름은 POST 바디로만 받고(URL 노출 없음), 렌더링에만 쓰고 저장하지 않는다(NFR-6)."""
    captured = {}

    async def fake_html_to_pdf(html_str: str, layout: str = "booklet") -> bytes:
        # Chromium 없이도 돌게 렌더 단계만 대체 — HTML 생성(Jinja2)은 실제로 수행된다.
        captured["html"] = html_str
        captured["layout"] = layout
        return b"%PDF-1.4 fake"

    monkeypatch.setattr(pdf_service, "html_to_pdf", fake_html_to_pdf)

    stories = (await client.get("/api/stories")).json()
    resp = await client.post(
        f"/api/stories/{stories[0]['id']}/generate",
        json={"lang": "ko", "child_speech": "두꺼비가 도와줬어요."},
    )
    session_id = resp.json()["session_id"]

    # (a) 바디로 이름 전달 → PDF 200
    resp = await client.post(
        f"/api/sessions/{session_id}/pdf", json={"author_name": AUTHOR_NAME}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    # 이름은 렌더링에는 반영된다.
    assert AUTHOR_NAME in captured["html"]

    # (b) 그 이름이 sessions 행 어디에도 저장되지 않음 — 컬럼 전체를 문자열로 훑는다.
    agen = app.dependency_overrides[get_session]()
    db = await agen.__anext__()
    try:
        rows = (await db.execute(sa.text("SELECT * FROM sessions"))).mappings().all()
    finally:
        await agen.aclose()
    assert rows
    for row in rows:
        assert AUTHOR_NAME not in " ".join(str(v) for v in row.values())
        assert "author" not in " ".join(row.keys()).lower()


async def test_pdf_get_is_demo_fallback_only(client: AsyncClient):
    """(c) demo GET 폴백은 그대로 동작하고, 숫자 세션 GET 은 POST 안내로 막힌다."""
    resp = await client.get("/api/sessions/demo/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    resp = await client.get("/api/sessions/1/pdf")
    assert resp.status_code == 400
    assert "POST" in resp.json()["detail"]


@pytest.mark.pdf
async def test_pdf_render_bytes():
    """Playwright 실제 렌더링 — 무거우므로 마커 분리(pytest -m 'not pdf' 로 스킵)."""
    story = Story(
        title="콩쥐팥쥐",
        emoji="🐸",
        keyword="권선징악",
        intro_summary="",
        intro_image="",
        bibliography={"title": "콩쥐팥쥐전", "year": "1926", "publisher": "미상"},
        fixed_keywords=[],
        recommend_books=[],
    )
    session = StorySession(
        story_id=1,
        lang="ko",
        child_speech="...",
        pages=[
            {"no": 1, "ko": "두꺼비가 독을 막았어요.", "en": "The toad blocked it."},
            {"no": 2, "ko": "물을 채웠어요.", "en": "Filled with water."},
            {"no": 3, "ko": "잔치에 갔어요.", "en": "Went to the party."},
        ],
        keywords=["권선징악"],
    )
    data = await pdf_service.render_pdf(story, session, author_name="김토스")
    assert isinstance(data, bytes)
    assert len(data) > 0
