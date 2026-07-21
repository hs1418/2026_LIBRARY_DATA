"""배포 환경 부트스트랩 — 테이블 생성 + 시드.

로컬 워크숍 환경은 alembic 으로 스키마를 관리하지만, 배포본(Render)은
디스크가 재기동마다 초기화되는 임시 볼륨이라 매번 새로 만들어야 한다.
배포의 목적이 제출 링크·시연 영상 녹화이고 세션 데이터를 보존할 필요가
없으므로(ADR-0003), 마이그레이션 이력 대신 create_all 로 단순화한다.

start 커맨드에서 uvicorn 앞에 한 번 실행한다:
    python -m app.bootstrap && uvicorn app.main:app ...
"""
import asyncio

from app.db import Base, engine
from app.seed import seed


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed()  # 이미 있으면 건너뛴다(멱등)


if __name__ == "__main__":
    asyncio.run(main())
