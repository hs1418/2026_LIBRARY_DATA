"""골든 패스 스모크 테스트 — SQLite(aiosqlite) 인메모리 + LLM/정보나루 mock.

검증:
① 시드 후 GET /api/stories 200
② POST generate → session 생성·pages 3개·html.escape 적용(child_speech 의 <script> 이스케이프)
③ GET /api/sessions/{id} 200
④ recommendations 폴백 경로(정보나루 실패 시 fallback:true)
PDF 는 별도 테스트(@pytest.mark.pdf)로 분리 — 서비스 함수를 직접 1회 호출해 바이트 > 0 확인.
"""
import json

import httpx
import pytest
import pytest_asyncio
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
    async def fake_call_gemini(payload: dict, timeout: float) -> dict:
        is_generate = (
            payload.get("generationConfig", {}).get("response_mime_type")
            == "application/json"
        )
        if is_generate:
            # 아이 구술을 그대로 페이지에 반영(escape 전) — _normalize 가 escape 한다.
            text = json.dumps(
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
        else:
            text = "이어서 읽으면 좋은 이야기예요"
        return {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    async def fake_srch_books(query: str):
        # 정보나루 장애 시뮬레이션 → 폴백 경로 유도
        raise httpx.ConnectError("simulated data4library outage")

    monkeypatch.setattr(llm, "_call_gemini", fake_call_gemini)
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
    assert recs["books"][0]["call_number"] == "813.8-ㄷ"
    # 프론트 계약: comment 키 존재(문구 생성 성공 시 문자열, 실패 시 null)
    assert "comment" in recs


async def test_story_not_found(client: AsyncClient):
    resp = await client.get("/api/stories/9999")
    assert resp.status_code == 404


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
