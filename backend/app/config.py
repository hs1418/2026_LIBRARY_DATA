"""환경변수 로드 (pydantic-settings). 시크릿 하드코딩 금지 — .env.example 가 계약."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DB — 테스트는 이 값을 override 해 SQLite(aiosqlite)로 돌린다.
    database_url: str = "postgresql+asyncpg://library:library@localhost:5433/library"

    # Gemini (LLM)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # 정보나루
    data4library_key: str = ""

    # 국가서지 API
    nl_api_key: str = ""


settings = Settings()
