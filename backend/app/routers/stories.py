"""Story 라우터 — 서가 목록/상세(정적), generate(런타임 LLM)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Session, Story
from app.schemas import GenerateRequest, GenerateResponse, StoryCard, StoryDetail
from app.services import llm

router = APIRouter(prefix="/api/stories", tags=["stories"])


@router.get("", response_model=list[StoryCard])
async def list_stories(db: AsyncSession = Depends(get_session)) -> list[Story]:
    result = await db.execute(select(Story).order_by(Story.id))
    return list(result.scalars().all())


@router.get("/{story_id}", response_model=StoryDetail)
async def get_story(
    story_id: int, db: AsyncSession = Depends(get_session)
) -> Story:
    story = await db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="story not found")
    return story


@router.post("/{story_id}/generate", response_model=GenerateResponse)
async def generate(
    story_id: int,
    payload: GenerateRequest,
    db: AsyncSession = Depends(get_session),
) -> GenerateResponse:
    story = await db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="story not found")

    try:
        # intro_summary(원작 앞부분)를 프롬프트에 함께 넣는다 — AI팀 user_prompt 설계.
        pages, keywords = await llm.generate_pages(
            payload.lang, payload.child_speech, story.intro_summary
        )
    except llm.LLMError:
        # 재시도 후에도 실패 — 세션 종료가 아니라 재입력 유도(ADR-0004 1계층).
        raise HTTPException(
            status_code=503, detail="generation failed, please try again"
        ) from None

    session = Session(
        story_id=story.id,
        lang=payload.lang,
        child_speech=payload.child_speech,  # 이미 저장 전 escape 는 pages 에만 필요; 원문 보관
        pages=pages,
        keywords=keywords,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return GenerateResponse(
        session_id=session.id, pages=pages, keywords=keywords
    )
