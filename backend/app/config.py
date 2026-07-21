"""환경변수 로드 (pydantic-settings). 시크릿 하드코딩 금지 — .env.example 가 계약."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env는 CWD가 아니라 backend/ 기준으로 찾는다 — uvicorn --app-dir 등
# 다른 위치에서 실행해도 로드되도록 절대경로 고정.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DB — 테스트는 이 값을 override 해 SQLite(aiosqlite)로 돌린다.
    database_url: str = "postgresql+asyncpg://library:library@localhost:5433/library"

    # Groq (LLM) — Llama 3.1 8B instant
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # 정보나루
    data4library_key: str = ""

    # 국가서지 API
    nl_api_key: str = ""


settings = Settings()
