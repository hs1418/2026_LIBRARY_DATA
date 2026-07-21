"""Groq/Llama 3.1 LLM 클라이언트 — 구술 → 페이지 분할 동화(한/영) + 키워드.

프롬프트 출처: hs1418/2026_LIBRARY_DATA backend/llm.py (v1.2)
             — 프롬프트(system_prompt·user_prompt) 수정은 AI담당자 소관.

정책(ADR-0004): 전체 호출 타임아웃 15초 + 실패 시 1회 재시도(우리 배관 책임 — 원본엔 없음).
보안(ARCHITECTURE §3-3): html.escape 는 _normalize 한 곳에서만 적용한다.
             AI팀 원본은 모듈 안에서 escape 하지만, 우리는 _normalize 로 이스케이프
             지점을 단일화했다(모듈 내 중복 escape 제거 → 이중 이스케이프 방지).
"""
import asyncio
import html
import json
import re

from groq import AsyncGroq, GroqError

from app.config import settings

LLM_TIMEOUT = 15.0
LLM_MAX_ATTEMPTS = 2  # 최초 1회 + 재시도 1회

# ── 프롬프트: AI팀 원본(v1.2)을 한 글자도 바꾸지 않고 그대로 이식 ──────────────
# v1.2 고도화된 시스템 프롬프트 (명칭 보존 및 정확한 영문 고유명사 지침 추가)
_SYSTEM_PROMPT = """
    당신은 대한민국 최고의 아동용 전래동화 전문 작가이자 번역가입니다.
    전달받은 [원작 앞부분 요약]과 [아동의 구술 입력]을 유기적으로 이어 붙여 따뜻한 결말을 완성하세요.

    [동화체 작성 지침 (아이 말투 살리기)]:
    1. 고유명사 유지: 등장인물이나 동물 이름(예: 콩쥐->Kongjwi, 두꺼비->Toad)을 환각(Hallucination)으로 변형하거나 오역하지 마세요.
2. 문체: 아동이 친근감을 느낄 수 있는 높임 동화체(~했지요, ~했답니다, ~했지 뭐예요)를 사용하세요.
    3. 각색: 아동의 구술 데이터가 파편화되어 있거나 짧더라도, 문맥을 자연스럽게 보완하여 동화의 서사 구조를 완성하세요.
    4. 분량 및 페이지: 전체 결말을 반드시 3~5개의 페이지("pages")로 분할하세요. 각 페이지는 그림책 한 면에 들어갈 1~2문장 내외로 구성하세요.

    [JSON 파싱 가드레일 (엄격 적용)]:
    1. 출력 형태: 오직 순수한 JSON 객체 하나만 반환하세요.
    2. 절대 금지 사항: 인사말, 설명, 서론, 결론, Markdown 코드 블록(```json)을 단 한 글자도 출력하지 마세요.
    3. 스키마 준수: Key 이름("pages", "no", "ko", "en", "keywords")을 절대 변경하지 마세요.
    """


def _build_messages(intro_summary: str, child_speech_accumulated: str) -> list[dict]:
    """AI팀 원본 user_prompt(v1.2)를 그대로 조립 — 문구 수정은 AI담당자 소관."""
    user_prompt = f"""
    [동화 앞부분 요약]: {intro_summary}
    [아이의 구술 입력]: {child_speech_accumulated}

    [JSON 반환 포맷 예시]:
    {{
      "pages": [
        {{ "no": 1, "ko": "한글 문장 1", "en": "English sentence 1" }},
        {{ "no": 2, "ko": "한글 문장 2", "en": "English sentence 2" }}
      ],
      "keywords": ["키워드1", "키워드2"]
    }}
    """
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
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
    """파싱 결과를 검증하고 모든 텍스트에 html.escape() 적용.

    이스케이프 단일 지점: LLM 텍스트는 여기서만 escape 한다. Groq 응답을 받는
    _call_groq/_build_messages 어디에서도 escape 하지 않는다(이중 이스케이프 방지).
    """
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


async def _call_groq(messages: list[dict]) -> str:
    """Groq Llama 3.1 호출 — 네트워크 seam(테스트는 이 함수를 monkeypatch 한다).

    반환: 모델이 낸 순수 JSON 문자열(escape 하지 않음 — 단일 escape 는 _normalize).
    """
    client = AsyncGroq(api_key=settings.groq_api_key)
    response = await client.chat.completions.create(
        messages=messages,
        model=settings.groq_model,
        response_format={"type": "json_object"},
        temperature=0.5,  # 고유명사 변형 방지를 위해 0.5 로 안정화(AI팀 v1.2)
    )
    return response.choices[0].message.content or ""


async def generate_pages(
    lang: str, child_speech: str, intro_summary: str = ""
) -> tuple[list[dict], list[str]]:
    """구술 → (pages, keywords). 실패/파싱오류 시 1회 재시도, 그래도 실패하면 LLMError.

    lang 은 세션 저장·API 대칭용으로 받되, AI팀 프롬프트가 한/영 병기를 항상 생성하므로
    프롬프트에는 사용하지 않는다. 전체 Groq 호출은 15초 타임아웃으로 감싼다(ADR-0004).
    """
    messages = _build_messages(intro_summary, child_speech)
    last_error: Exception | None = None

    for _ in range(LLM_MAX_ATTEMPTS):
        try:
            raw = await asyncio.wait_for(_call_groq(messages), timeout=LLM_TIMEOUT)
            data = _extract_json(raw)
            return _normalize(data)
        except (
            TimeoutError,
            GroqError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            continue

    raise LLMError(
        f"generate_pages failed after {LLM_MAX_ATTEMPTS} attempts: {last_error}"
    )
