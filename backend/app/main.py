"""FastAPI 앱 진입점 — 라우터 등록, frontend/ 정적 마운트, /health."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import sessions, stories

app = FastAPI(title="우리 전래동화 AI 도서관")

app.include_router(stories.router)
app.include_router(sessions.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# 디자이너 목업 기반 프론트를 루트에 마운트(html=True). 라우터(/api, /health) 등록 뒤에 둔다.
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
