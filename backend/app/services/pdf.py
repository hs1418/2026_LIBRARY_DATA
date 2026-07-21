"""PDF 렌더링 — Jinja2(templates/book.html) → Playwright(Chromium) A5 PDF 바이트.

poc_pdf.py 의 검증된 패턴 그대로: width 148mm / height 210mm / print_background=True.
Jinja2 autoescape 필수(§3-3 XSS 차단선). session id 가 "demo" 면 오프라인 폴백 PDF 서빙.
WeasyPrint 금지(ADR-0006, Windows GTK 문제).
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from app.models import Session, Story

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
FALLBACK_PDF = STATIC_DIR / "fallback_sample.pdf"

# autoescape 를 켜 둔 상태 유지가 이 프로젝트의 유일한 PDF XSS 차단선(§3-3).
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_book_html(story: Story, session: Session, author_name: str = "") -> str:
    """book.html 을 데이터로 채워 HTML 문자열 반환."""
    template = _env.get_template("book.html")
    return template.render(
        story=story,
        pages=session.pages or [],
        author_name=author_name,
    )


async def html_to_pdf(html_str: str) -> bytes:
    """HTML → A5 PDF 바이트 (poc_pdf.py 패턴)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html_str, wait_until="load")
            return await page.pdf(
                width="148mm",
                height="210mm",
                print_background=True,
            )
        finally:
            await browser.close()


async def render_pdf(story: Story, session: Session, author_name: str = "") -> bytes:
    """Story/Session → A5 PDF 바이트."""
    return await html_to_pdf(render_book_html(story, session, author_name))


def fallback_pdf_bytes() -> bytes | None:
    """오프라인 최종 방어선 — static/fallback_sample.pdf (없으면 None)."""
    if FALLBACK_PDF.exists():
        return FALLBACK_PDF.read_bytes()
    return None
