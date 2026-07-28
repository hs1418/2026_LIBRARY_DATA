"""10편 시드 파서 + 표지 렌더 회귀 테스트 (전부 mock/로컬 파일 — 실키 불필요).

검증:
(a) 시드 파서가 AI팀 파일에서 10편·각 5권을 정확히 읽는다
(b) GET /api/stories 가 10편 + cover_image 를 준다
(c) 표지 이미지가 있는 이야기의 PDF HTML 에 그림 표지가 인라인된다(제목 텍스트는 생략)
(d) cover_image 가 비면 이모지+제목 표지로 폴백한다
(e) 실서지가 없는 이야기의 판권기는 연도를 지어내지 않고 구전 원작 문구로 폴백한다
"""
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.models import Session as StorySession
from app.models import Story
from app.seed import COVER_SLUGS, SEED_FILE, parse_seed_file
from app.services import pdf as pdf_service

EXPECTED_TITLES = [
    "콩쥐팥쥐전",
    "흥부놀부전",
    "해님달님전",
    "금도끼 은도끼",
    "별주부전",
    "은혜 갚는 까치",
    "선녀와 나무꾼",
    "심청전",
    "단군신화 (곰과 호랑이)",
]

# 시드에 실서지가 있는 이야기는 콩쥐팥쥐전 하나뿐 — 나머지는 의도적으로 비어 있다.
TITLE_WITH_BIBLIOGRAPHY = "콩쥐팥쥐전"


# ── (a) 파서 ────────────────────────────────────────────────────────────────
def test_parser_reads_active_stories_with_five_books_each():
    stories = parse_seed_file()

    assert SEED_FILE.is_file()
    assert [s["title"] for s in stories] == EXPECTED_TITLES
    for story in stories:
        assert len(story["recommend_books"]) == 5, story["title"]
        assert story["emoji"]
        assert story["intro_summary"]
        # KEYWORD 는 콤마 목록 → fixed_keywords, 대표 키워드는 첫 번째.
        assert len(story["fixed_keywords"]) >= 2
        assert story["keyword"] == story["fixed_keywords"][0]


def test_parser_maps_book_fields():
    """'제목 | 저자 | 출판사 | 청구기호' 네 칸이 계약 필드로 들어간다."""
    first = parse_seed_file()[0]["recommend_books"][0]

    assert first == {
        "title": "콩쥐팥쥐",
        "author": "이성실 글 ; 박완서 그림",
        "publisher": "보림",
        "call_number": "813.8-보64ㅋ-2",
    }
    # AI팀 원본 필드명(call_no)이 새지 않아야 한다(프론트 계약: call_number).
    assert "call_no" not in first


def test_parser_assigns_cover_and_keeps_bibliography_honest():
    stories = parse_seed_file()

    for story in stories:
        slug = COVER_SLUGS.get(story["title"], "")
        if not slug:
            # 표지가 없는 이야기(예: 오탈자로 제외)는 빈 값 → 이모지 표지로 폴백한다.
            assert story["cover_image"] == ""
            continue
        assert story["cover_image"] == f"/static/covers/{slug}.jpg"
        # 표지 파일이 실제로 있어야 한다(리사이즈본 누락 회귀 방지).
        assert (pdf_service.STATIC_DIR / "covers" / f"{slug}.jpg").is_file()

        if story["title"] == TITLE_WITH_BIBLIOGRAPHY:
            assert story["bibliography"]["publisher"]
            assert story["bibliography"]["year"]
        else:
            # 발행연도·발행처를 지어내지 않는다(허위 서지 방지).
            assert story["bibliography"] == {}


# ── (b) 서가 API ────────────────────────────────────────────────────────────
async def test_list_stories_returns_active_stories_with_cover_image(full_client: AsyncClient):
    resp = await full_client.get("/api/stories")
    assert resp.status_code == 200

    stories = resp.json()
    assert len(stories) == len(EXPECTED_TITLES)
    assert [s["title"] for s in stories] == EXPECTED_TITLES
    # 표지가 매핑된 이야기는 경로를, 없는 이야기(오탈자로 제외 등)는 빈 값을 준다.
    with_cover = [s for s in stories if s["cover_image"]]
    assert with_cover, "표지가 하나도 붙지 않았다"
    for story in with_cover:
        assert story["cover_image"].startswith("/static/covers/")
        assert story["cover_image"].endswith(".jpg")


# ── (c)(d) 표지 렌더 ────────────────────────────────────────────────────────
def _story(cover_image: str = "", bibliography: dict | None = None) -> Story:
    return Story(
        title="흥부놀부전",
        emoji="🪺",
        keyword="우애",
        intro_summary="제비가 박씨를 물어다 주었어요.",
        intro_image="",
        cover_image=cover_image,
        bibliography=bibliography or {},
        fixed_keywords=[],
        recommend_books=[],
    )


def _session(lang: str = "ko") -> StorySession:
    return StorySession(
        story_id=1,
        lang=lang,
        child_speech="...",
        pages=[
            {"no": 1, "ko": "박이 열렸어요.", "en": "A gourd grew."},
            {"no": 2, "ko": "보물이 나왔어요.", "en": "Treasure came out."},
            {"no": 3, "ko": "함께 잘 살았어요.", "en": "They lived well."},
        ],
        keywords=["보은"],
    )


def test_cover_image_is_inlined_and_replaces_title_text():
    story = _story(cover_image="/static/covers/heungbu.jpg")
    html = pdf_service.render_book_html(story, _session(), author_name="김토스")

    # 그림 표지는 base64 인라인(file:// 은 about:blank 문서에서 차단된다 — pdf.cover_data_uri).
    assert "data:image/jpeg;base64," in html
    assert 'class="cover-photo-img"' in html
    # 표지 이미지에 제목이 이미 그려져 있으므로 kicker·제목 텍스트는 찍지 않는다.
    assert 'class="cover-title"' not in html
    assert "나만의 상상 동화책" not in html
    # 작가명은 남는다.
    assert "김토스 어린이" in html


def test_cover_falls_back_to_emoji_when_no_image():
    html = pdf_service.render_book_html(_story(), _session(), author_name="김토스")

    assert "data:image/jpeg;base64," not in html
    assert 'class="cover-emoji"' in html
    assert 'class="cover-title"' in html
    assert "나만의 상상 동화책" in html
    assert "🪺" in html


def test_cover_falls_back_when_file_missing():
    """시드 경로가 있어도 파일이 없으면 이모지 표지로 떨어진다(자산 유실 안전망)."""
    html = pdf_service.render_book_html(
        _story(cover_image="/static/covers/does_not_exist.jpg"), _session()
    )

    assert "base64," not in html
    assert 'class="cover-emoji"' in html


@pytest.mark.parametrize(
    "path",
    ["", "covers/heungbu.jpg", "/static/../.env", "/etc/passwd", "/static/covers/../../.env"],
)
def test_cover_data_uri_rejects_paths_outside_static(path: str):
    assert pdf_service.cover_data_uri(path) == ""


# ── (e) 판권기 서지 폴백 ────────────────────────────────────────────────────
def test_colophon_falls_back_to_oral_tradition_credit():
    """서지가 없는 9편 — 발행연도를 창작하지 않고 구전 원작임을 밝힌다."""
    html = pdf_service.render_book_html(_story(), _session())

    assert "원작 : 옛이야기(구전) — 국립중앙도서관 소장 자료 기반" in html
    # 실서지가 없으니 연도/발행처가 원작 줄에 끼어들 여지도 없다.
    assert "1926" not in html


def test_colophon_prints_real_bibliography_when_present():
    story = _story(
        bibliography={
            "title": "콩쥐팥쥐전",
            "publisher": "영창서관 (원작 출판) / 보림 (현대 재해석)",
            "year": "1920s (딱지본 원전) / 2018 (표준 서지)",
            "source": "국립중앙도서관 국가서지",
        }
    )
    html = pdf_service.render_book_html(story, _session())

    assert "영창서관" in html
    assert "1920s" in html
    assert "국립중앙도서관 국가서지" in html
    assert "옛이야기(구전)" not in html


def test_colophon_credit_is_localised_for_en():
    html = pdf_service.render_book_html(_story(), _session(lang="en"))
    assert "passed down orally" in html


def test_cover_files_are_ascii_slugs():
    """표지 파일명은 ASCII slug 여야 한다(URL·파일시스템 안전)."""
    covers = sorted(p.name for p in (pdf_service.STATIC_DIR / "covers").glob("*.jpg"))

    # 매핑에 쓰이는 표지가 모두 존재해야 한다. 폴더에 매핑 밖 파일(제외된 표지 등)이
    # 남아 있는 것은 허용한다 — 재생성 후 되살릴 수 있게 파일은 지우지 않는다.
    mapped = sorted(f"{slug}.jpg" for slug in COVER_SLUGS.values())
    assert mapped
    assert set(mapped) <= set(covers)
    for name in mapped:
        assert name.isascii()
        assert Path(name).stem.replace("_", "").isalnum()
