"""FastAPI 앱 진입점 — 라우터 등록, frontend/ 정적 마운트, /health, 액세스 로그 마스킹."""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import sessions, stories


class _StripQueryStringFilter(logging.Filter):
    """uvicorn 액세스 로그의 요청 라인에서 쿼리스트링을 잘라낸다.

    아이 이름 등 개인정보가 URL 에 실려 로그에 남는 것을 원천 차단(NFR-6 / ADR-0005).
    특정 파라미터가 아니라 '?' 이후 전체를 마스킹하므로 향후 추가되는 파라미터에도 적용된다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn.access 포맷: (client_addr, method, full_path, http_version, status_code)
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path = args[2]
            if "?" in path:
                record.args = (
                    args[0],
                    args[1],
                    path.split("?", 1)[0] + "?<masked>",
                    args[3],
                    args[4],
                )
        return True


# 모듈 로드 시점에 부착 — uvicorn 이 로거를 설정한 뒤 앱을 import 하므로 필터가 유지된다.
logging.getLogger("uvicorn.access").addFilter(_StripQueryStringFilter())

app = FastAPI(title="우리 전래동화 AI 도서관")

app.include_router(stories.router)
app.include_router(sessions.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# 딱지본 스캔 등 정적 자산. 루트 마운트보다 먼저 걸어야 가려지지 않는다.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# 디자이너 목업 기반 프론트를 루트에 마운트(html=True). 라우터(/api, /health) 등록 뒤에 둔다.
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
