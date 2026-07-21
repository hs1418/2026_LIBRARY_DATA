"""Session 라우터 — 결과 조회, PDF 렌더링, 추천(정보나루→LLM)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Session, Story
from app.schemas import RecommendationsResponse, SessionResult
from app.services import data4library, pdf

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


async def _load_session(session_id: int, db: AsyncSession) -> Session:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.get("/{session_id}", response_model=SessionResult)
async def get_session_result(
    session_id: int, db: AsyncSession = Depends(get_session)
) -> Session:
    return await _load_session(session_id, db)


@router.get("/{session_id}/pdf")
async def get_session_pdf(
    session_id: str,
    author_name: str = Query(default="", max_length=50),
    db: AsyncSession = Depends(get_session),
) -> Response:
    # 오프라인 최종 방어선(ADR-0004 3계층): id="demo" → 사전 상비 샘플 PDF 즉시 서빙.
    if session_id == "demo":
        data = pdf.fallback_pdf_bytes()
        if data is None:
            raise HTTPException(status_code=404, detail="fallback sample not available")
        return Response(content=data, media_type="application/pdf")

    try:
        sid = int(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="session not found") from None

    session = await _load_session(sid, db)
    story = await db.get(Story, session.story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="story not found")

    # author_name 은 렌더링에만 사용하고 저장하지 않는다(NFR-6 / ADR-0005).
    data = await pdf.render_pdf(story, session, author_name)
    return Response(content=data, media_type="application/pdf")


@router.get("/{session_id}/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    session_id: int, db: AsyncSession = Depends(get_session)
) -> RecommendationsResponse:
    session = await _load_session(session_id, db)
    story = await db.get(Story, session.story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="story not found")

    keywords = session.keywords or story.fixed_keywords or []
    books, fallback = await data4library.search_recommendations(story, keywords)

    # comment(추천 문구)는 현 파이프라인에 생성 주체가 없어 null 고정(프론트 계약).
    # AI팀 산출물(llm/data4library 어느 쪽도)에 문구 생성기가 없다.
    return RecommendationsResponse(books=books, fallback=fallback, comment=None)
