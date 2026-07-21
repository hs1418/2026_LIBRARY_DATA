"""골든 패스 스모크 테스트 — SQLite(aiosqlite) 인메모리 + LLM/정보나루 mock.

검증:
① 시드 후 GET /api/stories 200
② POST generate → session 생성·pages 3개·html.escape 적용(child_speech 의 <script> 이스케이프)
③ GET /api/sessions/{id} 200
④ recommendations 폴백 경로(정보나루 실패 시 fallback:true)
⑤ POST /pdf — 이름은 바디로만 받고 렌더링에만 쓰이며 sessions 행에 저장되지 않음(NFR-6)
⑥ GET /pdf 는 demo 폴백 전용
실제 Playwright 렌더링은 @pytest.mark.pdf 로 분리 — 서비스 함수를 직접 1회 호출해 바이트 > 0 확인.
"""
import json

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Session as StorySession
from app.models import Story
from app.services import data4library, llm
from app.services import pdf as pdf_service

# child_speech 에 주입할 XSS 페이로드 — 응답에서 이스케이프됐는지 검증.
INJECTED_SPEECH = "두꺼비가 독을 막아줘서 <script>alert(1)</script>"

# PDF 요청에 실어 보내는 아이 이름 — 어디에도 저장되면 안 되는 값(NFR-6 / ADR-0005).
AUTHOR_NAME = "김토스"


@pytest_asyncio.fixture
async def client(monkeypatch):
    # --- SQLite 인메모리(StaticPool 로 단일 연결 공유) ---
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 시드 — 콩쥐팥쥐 1편
    async with TestSession() as session:
        session.add(
            Story(
                title="콩쥐팥쥐",
                emoji="🐸",
                keyword="권선징악",
                intro_summary="새어머니와 팥쥐는... 두꺼비가 나타나는데...",
                intro_image="/static/scans/kongjwi_intro.jpg",
                bibliography={
                    "title": "콩쥐팥쥐전",
                    "year": "1926",
                    "publisher": "미상(딱지본)",
                    "source": "국립중앙도서관 소장",
                },
                fixed_keywords=["권선징악", "보은", "지혜"],
                recommend_books=[
                    {"title": "은혜 갚은 두꺼비", "call_number": "813.8-ㄷ"},
                    {"title": "우렁각시", "call_number": "813.8-ㅇ"},
                ],
            )
        )
        await session.commit()

    async def override_get_session():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    # --- 외부 호출 mock ---
    async def fake_call_groq(messages: list[dict]) -> str:
        # Groq seam: 순수 JSON 문자열을 반환(escape 전) — _normalize 가 escape 한다.
        return json.dumps(
            {
                "pages": [
                    {"no": 1, "ko": INJECTED_SPEECH, "en": "The toad blocked it."},
                    {"no": 2, "ko": "콩쥐는 물을 채웠어요.", "en": "Filled with water."},
                    {"no": 3, "ko": "잔치에 갔어요.", "en": "Went to the party."},
                ],
                "keywords": ["권선징악", "두꺼비의보은", "창의적해결"],
            },
            ensure_ascii=False,
        )

    async def fake_srch_books(query: str):
        # 정보나루 장애 시뮬레이션 → 폴백 경로 유도
        raise httpx.ConnectError("simulated data4library outage")

    monkeypatch.setattr(llm, "_call_groq", fake_call_groq)
    monkeypatch.setattr(data4library, "_srch_books", fake_srch_books)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


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
    assert "<script>" not in page1_ko  # raw 태그가 남으면 안 됨
    assert "&lt;script&gt;" in page1_ko  # html.escape 적용 확인
    # 이스케이프 단일 지점 검증 — 이중 이스케이프(&amp;lt; / &amp;amp;)가 없어야 함.
    assert "&amp;lt;" not in page1_ko
    assert "&amp;amp;" not in page1_ko

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

    async def fake_html_to_pdf(html_str: str) -> bytes:
        # Chromium 없이도 돌게 렌더 단계만 대체 — HTML 생성(Jinja2)은 실제로 수행된다.
        captured["html"] = html_str
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
