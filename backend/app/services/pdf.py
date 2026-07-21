"""PDF 렌더링 — Jinja2(templates/book.html) → Playwright(Chromium) A4 가로 PDF 바이트.

디자인팀 템플릿(A4 반접기/철제본) 적용본:
A4 가로 한 장(297x210mm)에 A5 두 면을 배치하고 반으로 접어 책을 만든다.
쪽 순서는 [표지][원작 앞부분][아이 뒷이야기 xN][빈 그림페이지][판권기] 이고,
총 쪽수는 접기 구조상 4의 배수로 맞춘다(부족분은 판권기 바로 앞 빈 그림페이지).

Jinja2 autoescape 필수(§3-3 XSS 차단선). session id 가 "demo" 면 오프라인 폴백 PDF 서빙.
WeasyPrint 금지(ADR-0006, Windows GTK 문제).
"""
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from app.models import Session, Story

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
FALLBACK_PDF = STATIC_DIR / "fallback_sample.pdf"

# 접지 한 묶음(A4 앞/뒤 한 장)에 들어가는 쪽 수. 총 쪽수는 이 값의 배수여야 한다.
PAGES_PER_SIGNATURE = 4

# 개인정보 고지 — NFR-6 를 실물 인쇄본에 명시하는 장치라 언어와 무관하게 원문 그대로 유지한다.
PRIVACY_NOTICE = (
    "※ 본 도서에 사용된 꼬마 작가의 이름은 오직 현장 도서 인쇄만을 위해 "
    "일회성으로 사용되었으며, 서버에 저장되거나 수집되지 않았음을 알립니다."
)

PUBLISHER_KO = "우리 전래동화 AI 도서관"
PUBLISHER_EN = "Our Folktale AI Library"

_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# 화면 고정 문구만 언어별로 갈린다. 본문/원작 텍스트는 build_pages 가 한 언어만 담는다.
_LABELS: dict[str, dict[str, str]] = {
    "ko": {
        "cover_kicker": "나만의 상상 동화책",
        "draw_hint": "이곳에 그림을 그려보세요 🖍️",
        "default_author": "어린이 작가",
        "author_prefix": "글/그림 : ",
        "pubdate_label": "초판 발행일 : ",
        "author_label": "글/그림 : ",
        "publisher_label": "발행처 : ",
        "publisher": PUBLISHER_KO,
        "colophon_note": (
            "이 책은 AI 도서관 시스템을 통해 아이의 상상력으로 완성된 "
            "단 하나뿐인 창작 동화입니다."
        ),
    },
    "en": {
        "cover_kicker": "My Own Storybook",
        "draw_hint": "Draw your picture here 🖍️",
        "default_author": "a young author",
        "author_prefix": "Written & drawn by ",
        "pubdate_label": "First printed : ",
        "author_label": "Written & drawn by ",
        "publisher_label": "Published by : ",
        "publisher": PUBLISHER_EN,
        "colophon_note": (
            "This one-of-a-kind story was completed by a child's imagination "
            "through the AI Library system."
        ),
    },
}

# autoescape 를 켜 둔 상태 유지가 이 프로젝트의 유일한 PDF XSS 차단선(§3-3).
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def normalize_lang(lang: str | None) -> str:
    """지원 언어는 ko/en 둘뿐 — 그 밖의 값은 ko 로 떨어뜨린다."""
    return "en" if (lang or "").lower() == "en" else "ko"


def format_pubdate(created_at: datetime | None, lang: str) -> str:
    """판권기 발행일 — ko: 2026년 07월 21일 / en: July 21, 2026.

    로케일에 의존하지 않도록 월 이름을 직접 들고 쓴다(%B 는 서버 로케일을 탄다).
    """
    dt = created_at or datetime.now(UTC)
    if lang == "en":
        return f"{_MONTHS_EN[dt.month - 1]} {dt.day}, {dt.year}"
    return f"{dt.year}년 {dt.month:02d}월 {dt.day:02d}일"


def author_display(author_name: str, lang: str) -> str:
    """표지·판권기에 찍히는 작가 표기. 이름이 비면 자연스러운 기본값으로 대체한다."""
    name = (author_name or "").strip()
    if not name:
        return _LABELS[lang]["default_author"]
    return f"{name} 어린이" if lang == "ko" else name


def build_pages(story: Story, session: Session, lang: str) -> list[dict]:
    """책의 쪽 목록을 순서대로 만든다(총 쪽수는 4의 배수).

    [표지][원작 앞부분][아이 뒷이야기 xN][빈 그림페이지 x패딩][판권기]
    - 원작 앞부분(story.intro_summary)이 들어가야 "완전본"이 된다(감사 A-6).
    - 빈 페이지는 판권기 '바로 앞'에 넣는다 — 버리는 종이가 아니라 "더 그릴 공간".
    - 쪽번호는 원작 앞부분을 1 로 시작해 본문/빈 페이지까지 순차 증가.
      표지·판권기에는 번호가 없다.
    """
    body: list[dict] = [{"kind": "content", "text": story.intro_summary or ""}]
    for page in session.pages or []:
        body.append({"kind": "content", "text": (page.get(lang) or "").strip()})

    # 표지 1 + 본문 len(body) + 판권기 1 을 4의 배수로 올림 → 부족분이 빈 페이지 수.
    used = len(body) + 2
    padding = -used % PAGES_PER_SIGNATURE
    body.extend({"kind": "blank", "text": ""} for _ in range(padding))

    for index, page in enumerate(body, start=1):
        page["no"] = index

    return [
        {"kind": "cover", "text": "", "no": None},
        *body,
        {"kind": "colophon", "text": "", "no": None},
    ]


def impose(pages: list[dict]) -> list[dict]:
    """반접기 배치 — 4쪽 묶음마다 A4 두 장(바깥 면·안쪽 면)을 만든다.

    묶음 k(쪽 4k+1 ~ 4k+4):
      바깥 면 A4: 왼쪽=쪽(4k+4), 오른쪽=쪽(4k+1)
      안쪽 면 A4: 왼쪽=쪽(4k+2), 오른쪽=쪽(4k+3)
    각 장을 반 접어 순서대로 겹치면 책이 된다.
    """
    if len(pages) % PAGES_PER_SIGNATURE:
        raise ValueError(f"총 쪽수는 {PAGES_PER_SIGNATURE}의 배수여야 한다: {len(pages)}")

    sheets: list[dict] = []
    for start in range(0, len(pages), PAGES_PER_SIGNATURE):
        p1, p2, p3, p4 = pages[start : start + PAGES_PER_SIGNATURE]
        sheets.append({"side": "outer", "left": p4, "right": p1})
        sheets.append({"side": "inner", "left": p2, "right": p3})
    return sheets


def render_book_html(story: Story, session: Session, author_name: str = "") -> str:
    """book.html 을 데이터로 채워 HTML 문자열 반환."""
    lang = normalize_lang(session.lang)
    pages = build_pages(story, session, lang)
    template = _env.get_template("book.html")
    return template.render(
        story=story,
        session=session,
        lang=lang,
        t=_LABELS[lang],
        sheets=impose(pages),
        total_pages=len(pages),
        author=author_display(author_name, lang),
        pubdate=format_pubdate(session.created_at, lang),
        privacy_notice=PRIVACY_NOTICE,
    )


async def html_to_pdf(html_str: str) -> bytes:
    """HTML → A4 가로 PDF 바이트 (297x210mm, 반접기 배치본)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html_str, wait_until="load")
            return await page.pdf(
                width="297mm",
                height="210mm",
                print_background=True,
            )
        finally:
            await browser.close()


async def render_pdf(story: Story, session: Session, author_name: str = "") -> bytes:
    """Story/Session → A4 가로 반접기 PDF 바이트."""
    return await html_to_pdf(render_book_html(story, session, author_name))


def fallback_pdf_bytes() -> bytes | None:
    """오프라인 최종 방어선 — static/fallback_sample.pdf (없으면 None)."""
    if FALLBACK_PDF.exists():
        return FALLBACK_PDF.read_bytes()
    return None
