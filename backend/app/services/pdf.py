"""PDF 렌더링 — Jinja2(templates/book.html) → Playwright(Chromium) A4 가로 PDF 바이트.

디자인팀 템플릿(A4 반접기/철제본) 적용본:
A4 가로 한 장(297x210mm)에 A5 두 면을 배치하고 반으로 접어 책을 만든다.
쪽 순서는 [표지][원작 앞부분][아이 뒷이야기 xN][빈 그림페이지][판권기] 이고,
총 쪽수는 접기 구조상 4의 배수로 맞춘다(부족분은 판권기 바로 앞 빈 그림페이지).

Jinja2 autoescape 필수(§3-3 XSS 차단선). session id 가 "demo" 면 오프라인 폴백 PDF 서빙.
WeasyPrint 금지(ADR-0006, Windows GTK 문제).
"""
import base64
import logging
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from app.models import Session, Story

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
FALLBACK_PDF = STATIC_DIR / "fallback_sample.pdf"

STATIC_URL_PREFIX = "/static/"

# 접지 한 묶음(A4 앞/뒤 한 장)에 들어가는 쪽 수. 총 쪽수는 이 값의 배수여야 한다.
PAGES_PER_SIGNATURE = 4

# 개인정보 고지 — NFR-6 를 실물 인쇄본에 명시하는 장치라 언어와 무관하게 원문 그대로 유지한다.
PRIVACY_NOTICE = (
    "※ 본 도서에 사용된 꼬마 작가의 이름은 오직 현장 도서 인쇄만을 위해 "
    "일회성으로 사용되었으며, 서버에 저장되거나 수집되지 않았음을 알립니다."
)

PUBLISHER_KO = "우리 전래동화 상상 도서관"
PUBLISHER_EN = "Our Folktale Imagination Library"

_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# 화면 고정 문구만 언어별로 갈린다. 본문/원작 텍스트는 build_pages 가 한 언어만 담는다.
_LABELS: dict[str, dict[str, str]] = {
    "ko": {
        "cover_kicker": "나만의 상상 동화책",
        "edition_suffix": "(창작본)",
        "draw_hint": "이곳에 그림을 그려보세요 🖍️",
        "blank_label": "🖍️ 나만의 그림 페이지",
        "default_author": "어린이 작가",
        "author_prefix": "글/그림 : ",
        "pubdate_label": "초판 발행일 : ",
        "author_label": "글/그림 : ",
        "publisher_label": "발행처 : ",
        "publisher": PUBLISHER_KO,
        "original_label": "원작 : ",
        # 시드에 실서지가 없는 이야기용 폴백 — 발행연도를 지어내지 않는다(허위 서지 방지).
        "original_fallback": "원작 : 옛이야기(구전) — 국립중앙도서관 소장 자료 기반",
        "colophon_note": (
            "이 책은 상상 도서관에서 아이의 상상력으로 완성된 "
            "단 하나뿐인 창작 동화입니다."
        ),
    },
    "en": {
        "cover_kicker": "My Own Storybook",
        "edition_suffix": "(Original Edition)",
        "draw_hint": "Draw your picture here 🖍️",
        "blank_label": "🖍️ My own drawing page",
        "default_author": "a young author",
        "author_prefix": "Written & drawn by ",
        "pubdate_label": "First printed : ",
        "author_label": "Written & drawn by ",
        "publisher_label": "Published by : ",
        "publisher": PUBLISHER_EN,
        "original_label": "Original : ",
        "original_fallback": (
            "Original : a Korean folktale passed down orally — "
            "based on National Library of Korea holdings"
        ),
        "colophon_note": (
            "This one-of-a-kind story was completed by a child's imagination "
            "at the Imagination Library."
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


def original_credit(story: Story, lang: str) -> str:
    """판권기의 '원작' 한 줄.

    실서지(발행처·발행연도)가 확보된 이야기만 그 값을 찍는다. 시드에 서지가 없으면
    연도를 지어내는 대신 구전 원작임을 밝히는 일반 문구로 폴백한다 — 인쇄물에 허위
    서지가 박히면 심사·자료 신뢰도 리스크가 된다(전래동화 10편 중 9편이 이 경우).
    """
    bib = story.bibliography if isinstance(story.bibliography, dict) else {}
    parts = [
        str(bib.get(key, "")).strip()
        for key in ("title", "publisher", "year")
        if str(bib.get(key, "")).strip()
    ]
    if not parts:
        return _LABELS[lang]["original_fallback"]

    line = _LABELS[lang]["original_label"] + " · ".join(parts)
    source = str(bib.get("source", "")).strip()
    return f"{line} ({source})" if source else line


_COVER_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def cover_data_uri(cover_image: str) -> str:
    """표지 이미지 URL(/static/...) → base64 data URI. 없거나 못 읽으면 빈 문자열.

    왜 file:// 절대경로가 아니라 base64 인라인인가:
      html_to_pdf 는 page.set_content() 로 about:blank 문서에 HTML 을 심는다. 이 문서에서
      file:// 하위 리소스 로드는 Chromium 이 차단하므로(file 스킴은 non-file 오리진에서
      불러올 수 없다) 표지가 빈칸으로 렌더된다. data URI 는 문서 오리진과 무관하고
      wait_until="load" 시점에 디코딩이 끝나 있어 로드 타이밍 문제도 없다.
      표지 1장(약 0.5MB → base64 0.7MB)만 인라인하므로 HTML 크기도 감당 가능하다.

    빈 문자열을 반환하면 템플릿이 이모지 표지로 폴백한다(파일 유실 대비 안전망).
    """
    path = (cover_image or "").strip()
    if not path.startswith(STATIC_URL_PREFIX):
        return ""

    static_root = STATIC_DIR.resolve()
    # 시드가 넣는 값이지만 경로 조작은 원천 차단한다 — static/ 밖은 거부.
    target = (static_root / path[len(STATIC_URL_PREFIX) :]).resolve()
    if static_root not in target.parents or not target.is_file():
        logger.warning("표지 이미지를 찾지 못해 이모지 표지로 폴백: %s", path)
        return ""

    mime = _COVER_MIME.get(target.suffix.lower())
    if mime is None:
        logger.warning("표지 이미지 형식 미지원: %s", path)
        return ""

    encoded = base64.b64encode(target.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


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
    """중철(saddle-stitch) 배치.

    A4 여러 장을 통째로 겹쳐 가운데를 한 번 접는 제본이다. N쪽(4의 배수)일 때
    바깥 시트부터 안쪽으로 들어가며 쪽이 짝지어진다:

      시트 i(0-indexed): 바깥면 [쪽(N-2i) | 쪽(1+2i)]
                         안쪽면 [쪽(2+2i) | 쪽(N-1-2i)]

    예) 8쪽: 1면[8|1] 2면[2|7] 3면[6|3] 4면[4|5].
    2장을 겹쳐 한 번 접으면 표지→…→판권기가 순서대로 읽힌다.

    이전에는 4쪽 묶음마다 독립적으로 접는 방식이었는데, 8쪽 이상에서
    판권기가 겉표지 뒷면이 아니라 중간 시트로 밀려나 제본 순서가 어긋났다
    (디자인팀 피드백). 4쪽(단일 시트)에서는 두 방식 결과가 같다.
    """
    n = len(pages)
    if n % PAGES_PER_SIGNATURE:
        raise ValueError(f"총 쪽수는 {PAGES_PER_SIGNATURE}의 배수여야 한다: {n}")

    sheets: list[dict] = []
    for i in range(n // 2 // 2):  # 시트 수 = N/4
        # 1-indexed 쪽 번호를 0-indexed 리스트 접근으로.
        sheets.append({"side": "outer", "left": pages[n - 1 - 2 * i], "right": pages[2 * i]})
        sheets.append({"side": "inner", "left": pages[1 + 2 * i], "right": pages[n - 2 - 2 * i]})
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
        cover_src=cover_data_uri(story.cover_image),
        original_credit=original_credit(story, lang),
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
