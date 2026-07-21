"""A-1 회귀 테스트 — 이스케이프는 '렌더 계층 한 곳'에서만 걸린다.

배경: 예전에는 저장 시점(llm._normalize)에 html.escape 를 하고, 렌더 시점에
Jinja2 autoescape 가 한 번 더 escape 했다. 그 결과 아이가 가져갈 A5 인쇄물에
`&quot;` · `&amp;` 가 문자 그대로 찍혔다. API JSON 만 보는 테스트로는 못 잡는
버그였으므로, 여기서는 **렌더 결과물**(HTML 소스 / 실제 PDF 추출 텍스트)을 본다.

검증:
① HTML 소스: 값은 escape 된 상태 → XSS 차단선 유지(Chromium 불필요, 항상 실행)
② 실제 PDF 추출 텍스트: 엔티티 리터럴(`&quot;`·`&amp;`·`&lt;`)이 없어야 함
   + POST /api/sessions/{id}/pdf 가 200 + PDF 바이트를 반환 (PDF 엔드포인트 커버)
"""
import io
import json

import pytest
from httpx import AsyncClient
from pypdf import PdfReader

from app.models import Session as StorySession
from app.models import Story
from app.services import llm
from app.services import pdf as pdf_service

# 따옴표·앰퍼샌드·꺾쇠를 모두 담은 페이지. en 문장은 폰트가 없는 CI 에서도
# 추출이 안정적인 ASCII 라 어서션의 주 대상으로 쓴다.
QUOTE_KO = '두꺼비가 "괜찮아!" 하고 외쳤어. 콩쥐 & 두꺼비는 친구가 됐어요.'
QUOTE_EN = 'Toad shouted "OK!" and Kongjwi & Toad became friends. <b>END</b>'
XSS_KO = "<script>alert(1)</script>"

_PAGES = [
    {"no": 1, "ko": QUOTE_KO, "en": QUOTE_EN},
    {"no": 2, "ko": XSS_KO, "en": XSS_KO},
    {"no": 3, "ko": "끝.", "en": "The end."},
]

# 이 중 하나라도 렌더 결과에 보이면 이중 이스케이프다.
ENTITY_LITERALS = ["&quot;", "&amp;", "&lt;", "&gt;", "&#x27;", "&#39;"]


def _story() -> Story:
    return Story(
        title="콩쥐팥쥐",
        emoji="🐸",
        keyword="권선징악",
        intro_summary="",
        intro_image="",
        bibliography={"title": "콩쥐팥쥐전", "year": "1926", "publisher": "미상"},
        fixed_keywords=[],
        recommend_books=[],
    )


def _session() -> StorySession:
    return StorySession(
        story_id=1, lang="ko", child_speech="...", pages=_PAGES, keywords=["권선징악"]
    )


def _compact(text: str) -> str:
    """줄바꿈·자간 때문에 부분문자열 매칭이 깨지지 않게 공백을 전부 제거."""
    return "".join(text.split())


def test_html_source_escapes_once_only():
    """① HTML 소스 — 값은 딱 한 번 escape 된다(XSS 차단 유지 + 이중 이스케이프 없음)."""
    html_str = pdf_service.render_book_html(_story(), _session(), author_name="김토스")

    # XSS 차단선: raw <script> 가 소스에 실행 가능한 형태로 들어가면 안 된다.
    assert "<script>alert(1)</script>" not in html_str
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_str

    # 이중 이스케이프 금지: escape 된 엔티티의 & 가 또 escape 되면 &amp;lt; 가 된다.
    assert "&amp;lt;" not in html_str
    assert "&amp;amp;" not in html_str
    assert "&amp;quot;" not in html_str

    # 앰퍼샌드·따옴표는 정확히 한 겹만 escape 된 상태.
    assert "Kongjwi &amp; Toad" in html_str
    assert "&amp;amp; Toad" not in html_str


@pytest.mark.pdf
async def test_pdf_text_has_no_entity_literals():
    """② 실제 Chromium 렌더 — 추출 텍스트에 엔티티 리터럴이 남으면 실패."""
    data = await pdf_service.render_pdf(_story(), _session(), author_name="김토스")
    assert data.startswith(b"%PDF")

    reader = PdfReader(io.BytesIO(data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    compact = _compact(text)

    for literal in ENTITY_LITERALS:
        assert literal not in compact, f"이중 이스케이프 흔적: {literal}"

    # 사람이 읽는 문자로 제대로 찍혔는지(=단일 이스케이프가 렌더에서 풀렸는지).
    assert '"OK!"' in compact
    assert "Kongjwi&Toad" in compact
    # 태그는 텍스트로만 보여야 한다 — 해석됐다면 <b>/<script> 문자열 자체가 사라진다.
    assert "<b>END</b>" in compact
    assert "<script>alert(1)</script>" in compact


@pytest.mark.pdf
async def test_pdf_endpoint_returns_pdf_bytes(client: AsyncClient, monkeypatch):
    """POST /api/sessions/{id}/pdf 엔드포인트 자체 — 실제 렌더로 200 + PDF 바이트."""

    async def fake_call_groq(messages: list[dict]) -> str:
        return json.dumps({"pages": _PAGES, "keywords": ["보은"]}, ensure_ascii=False)

    monkeypatch.setattr(llm, "_call_groq", fake_call_groq)

    stories = (await client.get("/api/stories")).json()
    gen = await client.post(
        f"/api/stories/{stories[0]['id']}/generate",
        json={"lang": "ko", "child_speech": QUOTE_KO},
    )
    assert gen.status_code == 200
    # 저장·응답은 raw — 엔티티가 API 단계에서 이미 생기던 것이 원래 증상이었다.
    assert gen.json()["pages"][0]["ko"] == QUOTE_KO

    session_id = gen.json()["session_id"]
    resp = await client.post(
        f"/api/sessions/{session_id}/pdf", json={"author_name": "김토스"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    reader = PdfReader(io.BytesIO(resp.content))
    compact = _compact("\n".join(p.extract_text() or "" for p in reader.pages))
    for literal in ENTITY_LITERALS:
        assert literal not in compact, f"이중 이스케이프 흔적: {literal}"
