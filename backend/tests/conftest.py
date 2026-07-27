"""공용 픽스처 — SQLite(aiosqlite) 인메모리 앱 + 외부 호출 mock.

테스트는 전부 mock 경유라 실제 API 키(GROQ/정보나루) 없이 통과한다.
"""
import json

import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app
from app.models import Story
from app.seed import parse_seed_file
from app.services import data4library, llm

# child_speech 에 주입할 XSS 페이로드 — 저장은 raw, 렌더 계층에서 escape 되는지 검증한다.
INJECTED_SPEECH = "두꺼비가 독을 막아줘서 <script>alert(1)</script>"

# PDF 요청에 실어 보내는 아이 이름 — 어디에도 저장되면 안 되는 값(NFR-6 / ADR-0005).
AUTHOR_NAME = "김토스"


def kongjwi_story() -> Story:
    """기존 테스트가 기대하는 1편 픽스처(제목·추천 2권까지 그대로 유지)."""
    return Story(
        title="콩쥐팥쥐",
        emoji="🐸",
        keyword="권선징악",
        intro_summary="새어머니와 팥쥐는... 두꺼비가 나타나는데...",
        intro_image="/static/scans/kongjwi_intro.jpg",
        cover_image="/static/covers/kongjwi.jpg",
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


async def _build_client(monkeypatch, stories: list[Story]):
    # --- SQLite 인메모리(StaticPool 로 단일 연결 공유) ---
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSession() as session:
        session.add_all(stories)
        await session.commit()

    async def override_get_session():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    # --- 외부 호출 mock ---
    async def fake_call_groq(messages: list[dict]) -> str:
        # Groq seam: 모델이 낸 순수 JSON 문자열. 저장·응답 모두 raw 로 흘러간다.
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


@pytest_asyncio.fixture
async def client(monkeypatch):
    """콩쥐팥쥐 1편만 시딩된 클라이언트 — 기존 테스트 계약."""
    async for ac in _build_client(monkeypatch, [kongjwi_story()]):
        yield ac


@pytest_asyncio.fixture
async def full_client(monkeypatch):
    """AI팀 시드 파일 10편을 파서로 읽어 그대로 시딩한 클라이언트."""
    stories = [Story(**data) for data in parse_seed_file()]
    async for ac in _build_client(monkeypatch, stories):
        yield ac
