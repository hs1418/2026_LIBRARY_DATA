"""콩쥐팥쥐 1편 시딩 스크립트 — python -m app.seed.

서지/추천/키워드/앞부분 요약은 AI팀 시드(data/kongjwi_seed.txt) 실데이터로 갱신.
recommend_books 5권이 서비스 폴백의 진실 소스 — data4library.FALLBACK_BOOKS 와 동일(시드가 원본).
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
        "마음씨 착한 콩쥐는 새어머니와 팥쥐의 구박을 받으며 단독에 물 채우기, "
        "자갈밭 매기 등 힘든 일을 해냅니다. 그때 두꺼비와 소, 새들이 나타나 "
        "콩쥐를 도와주기 시작하는데..."
    ),
    "intro_image": "/static/scans/kongjwi_intro.jpg",
    "bibliography": {
        "title": "콩쥐팥쥐전",
        "isbn": "9788939502148",
        "publisher": "영창서관 (원작 출판) / 보림 (현대 재해석)",
        "year": "1920s (딱지본 원전) / 2018 (표준 서지)",
        "reg_no": "K2026-LIB-10492",
        "source": "국립중앙도서관 국가서지",
    },
    "fixed_keywords": ["권선징악", "효심", "지혜"],
    "recommend_books": [
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
