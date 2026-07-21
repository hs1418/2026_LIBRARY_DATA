"""async 엔진 / 세션 팩토리. 테스트는 create_all + override 로 SQLite 를 붙인다."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False, future=True)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI 의존성 — 요청 단위 세션. 테스트에서 override 대상."""
    async with SessionLocal() as session:
        yield session
