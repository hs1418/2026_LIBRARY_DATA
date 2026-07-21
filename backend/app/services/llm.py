"""Gemini LLM 클라이언트 — httpx 로 REST API 직접 호출(SDK 의존 최소화).

정책(ADR-0004): 타임아웃 15초 + 실패 시 1회 재시도. 파싱 실패도 재시도 1회에 포함.
보안(ARCHITECTURE §3-3): 모든 텍스트 필드에 html.escape() 적용 후 반환/저장.
"""
import html
import json
import re

import httpx

from app.config import settings

LLM_TIMEOUT = 15.0
LLM_MAX_ATTEMPTS = 2  # 최초 1회 + 재시도 1회

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# ── 프롬프트: AI담당자가 교체할 자리 ──────────────────────────────────────────
# W2 핸드오프로 구술→동화체 변환 프롬프트가 들어온다. pages[](3~5개) + keywords(3개)
# JSON 반환 사양(ADR-0005 / ARCHITECTURE §2-3)만 유지하면 본문은 자유롭게 교체 가능.
GENERATE_PROMPT = """너는 아이의 구술을 100년 전 딱지본 옛이야기의 뒷이야기로 정리하는 동화 작가다.
아이 말투의 순수함을 살리되 문장은 그림책에 어울리게 다듬어라.

주 언어: {lang}
아이 구술:
\"\"\"{child_speech}\"\"\"

아래 JSON 형식으로만 답하라(설명·마크다운 금지):
{{
  "pages": [{{"no": 1, "ko": "한국어 문장", "en": "English sentence"}}, ...],
  "keywords": ["키워드1", "키워드2", "키워드3"]
}}
- pages 는 3~5개. 각 페이지는 한 장면. 문장이 페이지 경계에서 자연스럽게 끊기게 나눠라.
- keywords 는 정확히 3개, 구술에서 뽑은 주제어.
"""
# ─────────────────────────────────────────────────────────────────────────────


class LLMError(RuntimeError):
    """재시도 후에도 생성/파싱에 실패."""


def _extract_json(text: str) -> dict:
    """모델 응답에서 JSON 블록을 추출·파싱. 코드펜스로 감싸도 처리."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in response")
    return json.loads(candidate[start : end + 1])


def _normalize(data: dict) -> tuple[list[dict], list[str]]:
    """파싱 결과를 검증하고 모든 텍스트에 html.escape() 적용."""
    raw_pages = data.get("pages")
    raw_keywords = data.get("keywords")
    if not isinstance(raw_pages, list) or not (3 <= len(raw_pages) <= 5):
        raise ValueError("pages must be a list of 3~5 items")
    if not isinstance(raw_keywords, list) or not raw_keywords:
        raise ValueError("keywords must be a non-empty list")

    pages: list[dict] = []
    for idx, page in enumerate(raw_pages, start=1):
        if not isinstance(page, dict):
            raise ValueError("each page must be an object")
        pages.append(
            {
                "no": int(page.get("no", idx)),
                "ko": html.escape(str(page.get("ko", ""))),
                "en": html.escape(str(page.get("en", ""))),
            }
        )
    keywords = [html.escape(str(k)) for k in raw_keywords]
    return pages, keywords


def _build_payload(lang: str, child_speech: str) -> dict:
    prompt = GENERATE_PROMPT.format(lang=lang, child_speech=child_speech)
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }


def _read_text(response_json: dict) -> str:
    return response_json["candidates"][0]["content"]["parts"][0]["text"]


async def _call_gemini(payload: dict, timeout: float) -> dict:
    """Gemini REST 호출 — 네트워크 seam(테스트는 이 함수를 monkeypatch 한다)."""
    url = GEMINI_URL.format(model=settings.gemini_model)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url, params={"key": settings.gemini_api_key}, json=payload
        )
        resp.raise_for_status()
        return resp.json()


async def generate_pages(lang: str, child_speech: str) -> tuple[list[dict], list[str]]:
    """구술 → (pages, keywords). 실패/파싱오류 시 1회 재시도, 그래도 실패하면 LLMError."""
    payload = _build_payload(lang, child_speech)
    last_error: Exception | None = None

    for _ in range(LLM_MAX_ATTEMPTS):
        try:
            response_json = await _call_gemini(payload, LLM_TIMEOUT)
            data = _extract_json(_read_text(response_json))
            return _normalize(data)
        except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            continue

    raise LLMError(f"generate_pages failed after {LLM_MAX_ATTEMPTS} attempts: {last_error}")


async def make_recommendation_blurb(keywords: list[str], titles: list[str]) -> str:
    """추천 문구 생성용 LLM 2차 호출. 짧은 타임아웃, 실패 시 문구 없이 빈 문자열."""
    prompt = (
        "다음 키워드로 창작한 아이에게, 이어서 읽으면 좋은 아래 도서들을 "
        "따뜻한 한 문장으로 추천하는 문구를 써라(30자 내외).\n"
        f"키워드: {', '.join(keywords)}\n"
        f"도서: {', '.join(titles)}\n"
        "문구만 출력하라."
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response_json = await _call_gemini(payload, 8.0)
        return html.escape(_read_text(response_json).strip())
    except (httpx.HTTPError, KeyError, json.JSONDecodeError):
        return ""
