"""A4 반접기(철제본) 템플릿 회귀 테스트 — 쪽 구성·배치 순서·언어·원작 포함.

배경: 기존 템플릿은 A5 낱장이라 "인쇄해서 접으면 책"이 되지 않았고, 원작 앞부분이
빠져 완전본이 아니었다(감사 A-6). 새 템플릿은 A4 가로 한 장에 A5 두 면을 얹고
4쪽 묶음마다 앞/뒤 두 장을 만든다.

검증:
(a) 아이 페이지 N=3,4,5 각각에서 총 쪽수가 4의 배수이고 A4 장수가 맞는지
(b) 배치 순서가 [4][1] / [2][3] 규칙대로인지 (HTML 렌더 결과로 확인)
(c) lang=en 이면 영어 본문만 나오는지 (한/영 병기 폐기)
(d) 원작 앞부분(story.intro_summary)이 책에 들어가는지
(e) 실제 Chromium 렌더 — 페이지 크기 297x210mm, 쪽수 일치
"""
import io
import re

import pytest
from pypdf import PdfReader

from app.models import Session as StorySession
from app.models import Story
from app.services import pdf as pdf_service

INTRO = "새어머니와 팥쥐는 콩쥐를 남겨두고 잔치에 가버렸어요."

# mm → PDF 포인트(1pt = 1/72in). 297x210mm = 841.89 x 595.28pt.
MM_TO_PT = 72 / 25.4


def _story() -> Story:
    return Story(
        title="콩쥐팥쥐",
        emoji="🐸",
        keyword="권선징악",
        intro_summary=INTRO,
        intro_image="",
        bibliography={"title": "콩쥐팥쥐전", "year": "1926", "publisher": "미상"},
        fixed_keywords=[],
        recommend_books=[],
    )


def _session(n: int, lang: str = "ko") -> StorySession:
    pages = [
        {"no": i, "ko": f"한국어 {i}번째 이야기.", "en": f"English story number {i}."}
        for i in range(1, n + 1)
    ]
    return StorySession(story_id=1, lang=lang, child_speech="...", pages=pages, keywords=[])


def _page_numbers(html: str) -> list[int]:
    """렌더된 HTML 에 찍힌 쪽번호를 등장 순서대로 뽑는다(= 실제 배치 순서)."""
    return [int(m) for m in re.findall(r'<div class="page-number">-\s*(\d+)\s*-</div>', html)]


# ── (a) 4의 배수 패딩 + A4 장수 ────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("n", "total", "sheets"),
    [(3, 8, 4), (4, 8, 4), (5, 8, 4), (6, 12, 6)],
)
def test_page_count_is_multiple_of_four(n: int, total: int, sheets: int):
    pages = pdf_service.build_pages(_story(), _session(n), "ko")
    assert len(pages) == total
    assert len(pages) % 4 == 0
    assert len(pdf_service.impose(pages)) == sheets

    # 구성: [표지][원작][아이 xN][빈 x패딩][판권기]
    assert pages[0]["kind"] == "cover"
    assert pages[1]["text"] == INTRO
    assert pages[-1]["kind"] == "colophon"

    blanks = [p for p in pages if p["kind"] == "blank"]
    assert len(blanks) == total - n - 3
    # 빈 페이지는 판권기 '바로 앞'에 몰려 있어야 한다.
    if blanks:
        assert all(p["kind"] == "blank" for p in pages[-1 - len(blanks) : -1])
        assert all(p["text"] == "" for p in blanks)

    # 쪽번호: 원작이 1, 표지·판권기는 번호 없음, 나머지는 순차 증가.
    assert pages[0]["no"] is None and pages[-1]["no"] is None
    assert [p["no"] for p in pages[1:-1]] == list(range(1, total - 1))


# ── (b) 반접기 배치 순서 ──────────────────────────────────────────────────────
def test_impose_saddle_stitch_8pages():
    """중철 배치 — 2장 겹쳐 한 번 접으면 1→8 순서로 읽힌다."""
    pages = [{"n": i} for i in range(1, 9)]
    sheets = pdf_service.impose(pages)

    assert len(sheets) == 4
    assert (sheets[0]["left"]["n"], sheets[0]["right"]["n"]) == (8, 1)  # 겉면: 판권기 | 표지
    assert (sheets[1]["left"]["n"], sheets[1]["right"]["n"]) == (2, 7)
    assert (sheets[2]["left"]["n"], sheets[2]["right"]["n"]) == (6, 3)
    assert (sheets[3]["left"]["n"], sheets[3]["right"]["n"]) == (4, 5)


def test_impose_cover_and_colophon_on_outer_sheet():
    """쪽수와 무관하게 표지(1)는 첫 시트 오른쪽, 판권기(N)는 첫 시트 왼쪽."""
    for n in (4, 8, 12):
        pages = [{"n": i} for i in range(1, n + 1)]
        sheets = pdf_service.impose(pages)
        assert sheets[0]["right"]["n"] == 1
        assert sheets[0]["left"]["n"] == n
        # 모든 쪽이 정확히 한 번씩 등장
        seen = sorted(s[side]["n"] for s in sheets for side in ("left", "right"))
        assert seen == list(range(1, n + 1))


def test_impose_rejects_non_multiple_of_four():
    with pytest.raises(ValueError):
        pdf_service.impose([{"n": i} for i in range(1, 7)])


def test_rendered_html_follows_imposition_order():
    """N=5 → 8쪽. 표지/판권기는 번호가 없으므로 본문 번호 순서로 배치를 확인한다."""
    html = pdf_service.render_book_html(_story(), _session(5))

    # a4-sheet 는 8쪽 → 4장.
    assert html.count('class="a4-sheet"') == 4
    # 중철 배치(논리쪽): 1면[판권기|표지] 2면[원작|뒷5] 3면[뒷4|뒷1] 4면[뒷2|뒷3]
    # 인쇄 번호(원작=1, 뒷1=2 … 뒷5=6): 표지·판권기는 번호 없음.
    assert _page_numbers(html) == [1, 6, 5, 2, 3, 4]


# ── (c) 언어 단일 출력 ───────────────────────────────────────────────────────
def test_lang_en_renders_english_only():
    session = _session(3, lang="en")
    html = pdf_service.render_book_html(_story(), session, author_name="Toast")

    for page in session.pages:
        assert page["en"] in html
        assert page["ko"] not in html


def test_lang_ko_renders_korean_only():
    session = _session(3, lang="ko")
    html = pdf_service.render_book_html(_story(), session, author_name="김토스")

    for page in session.pages:
        assert page["ko"] in html
        assert page["en"] not in html


def test_author_name_falls_back_when_empty():
    html = pdf_service.render_book_html(_story(), _session(3), author_name="")
    assert "어린이 작가" in html

    html_named = pdf_service.render_book_html(_story(), _session(3), author_name="김토스")
    assert "김토스 어린이" in html_named


def test_colophon_keeps_privacy_notice_verbatim():
    """NFR-6 고지 문구는 언어와 무관하게 원문 그대로 실물에 찍힌다."""
    for lang in ("ko", "en"):
        html = pdf_service.render_book_html(_story(), _session(3, lang=lang))
        assert "서버에 저장되거나 수집되지 않았음을 알립니다" in html


# ── (d)(e) 실제 Chromium 렌더 ────────────────────────────────────────────────
@pytest.mark.pdf
async def test_pdf_is_a4_landscape_with_expected_sheet_count():
    data = await pdf_service.render_pdf(_story(), _session(3), author_name="김토스")
    assert data.startswith(b"%PDF")

    reader = PdfReader(io.BytesIO(data))
    # N=3 → 8쪽 → A4 4장.
    assert len(reader.pages) == 4

    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        assert width == pytest.approx(297 * MM_TO_PT, abs=1.0)
        assert height == pytest.approx(210 * MM_TO_PT, abs=1.0)


@pytest.mark.pdf
async def test_pdf_contains_original_story_intro():
    """(d) 원작 앞부분이 PDF 안에 실제로 찍혀야 '완전본'이다(감사 A-6)."""
    data = await pdf_service.render_pdf(_story(), _session(3), author_name="김토스")
    reader = PdfReader(io.BytesIO(data))
    text = "".join("".join((p.extract_text() or "").split()) for p in reader.pages)

    assert "".join(INTRO.split()) in text
