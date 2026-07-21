"""콩쥐팥쥐 1편 시딩 스크립트 — python -m app.seed.

intro_summary / bibliography / recommend_books 는 W1 검증 후 실제 데이터로 교체할 placeholder.
"""
import asyncio

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Story

KONGJWI = {
    "title": "콩쥐팥쥐",
    "emoji": "🐸",
    "keyword": "권선징악",
    "intro_summary": (
        "새어머니와 팥쥐는 콩쥐에게 밑 빠진 독에 물을 채우라는 어려운 일을 시켜요. "
        "콩쥐가 울고 있는데, 커다란 두꺼비가 나타나는데..."
    ),
    "intro_image": "/static/scans/kongjwi_intro.jpg",
    "bibliography": {
        "title": "콩쥐팥쥐전",
        "year": "1926",
        "publisher": "미상(딱지본)",
        "source": "국립중앙도서관 소장",
        "note": "W1 검증 후 실제 서지로 교체",
    },
    "fixed_keywords": ["권선징악", "보은", "지혜"],
    "recommend_books": [
        {"title": "팥죽 할머니와 호랑이", "call_number": "813.8-ㅍ"},
        {"title": "우렁각시", "call_number": "813.8-ㅇ"},
        {"title": "해님 달님", "call_number": "813.8-ㅎ"},
        {"title": "은혜 갚은 두꺼비", "call_number": "813.8-ㄷ"},
        {"title": "선녀와 나무꾼", "call_number": "813.8-ㅅ"},
    ],
}


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        exists = await db.execute(select(Story).where(Story.title == KONGJWI["title"]))
        if exists.scalar_one_or_none() is not None:
            print("이미 시딩됨: 콩쥐팥쥐")
            return
        db.add(Story(**KONGJWI))
        await db.commit()
        print("시딩 완료: 콩쥐팥쥐")


if __name__ == "__main__":
    asyncio.run(seed())
