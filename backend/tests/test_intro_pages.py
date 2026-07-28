"""북뷰어용 원작 전문(intro_pages) 회귀 테스트 — 전부 로컬 파일 검사 (실키·네트워크 불필요).

원작을 결말까지 넘겨 봐야 아이가 "두꺼비 대신 호랑이가 왔으면" 같은 변형을 말할 수 있다.
페이지는 시드 파일 INTRO_PAGE_n 하나가 진실 소스이고, 그림·음성은 파일이 실제로 있을
때만 경로가 채워진다(표지·요약 음성과 같은 폴백 규칙).

검증:
(a) 파서가 콩쥐팥쥐전의 INTRO_PAGE_n 6개를 순서대로 읽는다
(b) 페이지가 없는 이야기는 빈 배열 → 프론트가 요약 카드로 폴백한다
(c) GET /api/stories/{id} 응답에 intro_pages 가 들어간다(목록에는 없다)
(d) 파일이 없는 삽화·음성은 빈 문자열
"""
from httpx import AsyncClient

from app import seed as seed_module
from app.models import Story
from app.seed import (
    build_intro_pages,
    page_audio_path,
    page_image_path,
    parse_seed_file,
    story_slug,
)

PAGED_TITLE = "콩쥐팥쥐전"
PAGED_SLUG = "kongjwi"
EXPECTED_PAGE_COUNT = 6


def _paged_story() -> dict:
    return next(s for s in parse_seed_file() if s["title"] == PAGED_TITLE)


# ── (a) 파서 ────────────────────────────────────────────────────────────────
def test_parser_reads_six_intro_pages_for_kongjwi():
    pages = _paged_story()["intro_pages"]

    assert len(pages) == EXPECTED_PAGE_COUNT
    # 번호는 시드에 적힌 값을 그대로 쓴다 — 자산 파일명(p{n})이 여기에 묶여 있다.
    assert [page["no"] for page in pages] == [1, 2, 3, 4, 5, 6]
    for page in pages:
        assert page["text"].strip(), page["no"]
        assert set(page) == {"no", "text", "image", "audio"}

    # 첫 쪽과 마지막 쪽(결말)이 시드 문장 그대로 실린다 — 요약이 아니라 전문이다.
    assert pages[0]["text"].startswith("콩쥐는 새어머니와 팥쥐랑 살았어요.")
    assert "행복하게 살았답니다" in pages[-1]["text"]


def test_intro_pages_do_not_leak_into_plain_fields():
    """INTRO_PAGE_n 이 INTRO_SUMMARY 등 일반 필드를 덮어쓰지 않는다."""
    story = _paged_story()

    assert story["intro_summary"].startswith("마음씨 착한 콩쥐는")
    assert "INTRO_PAGE" not in story["intro_summary"]
    assert story["keyword"] == "권선징악"


# ── (b) 페이지가 없는 이야기 ────────────────────────────────────────────────
def test_stories_without_intro_pages_get_empty_list():
    stories = parse_seed_file()
    paged = [s for s in stories if s["intro_pages"]]

    # 지금 원작 전문이 확정된 것은 콩쥐팥쥐전 하나뿐이다.
    assert [s["title"] for s in paged] == [PAGED_TITLE]
    for story in stories:
        if story["title"] != PAGED_TITLE:
            assert story["intro_pages"] == [], story["title"]


def test_build_intro_pages_is_empty_without_texts():
    assert build_intro_pages(PAGED_TITLE, {}) == []
    # 빈 본문 줄은 페이지로 세지 않는다(시드 오타가 빈 쪽을 만들지 않게).
    assert build_intro_pages(PAGED_TITLE, {1: "", 2: "   "}) == []


def test_seed_parser_still_builds_story_rows():
    """parse_seed_file 결과가 Story(**data) 계약을 유지한다(필드 추가 회귀)."""
    stories = [Story(**data) for data in parse_seed_file()]

    assert any(len(story.intro_pages) == EXPECTED_PAGE_COUNT for story in stories)


# ── (d) 자산 폴백 ───────────────────────────────────────────────────────────
def test_page_image_is_empty_when_file_missing(monkeypatch, tmp_path):
    """삽화는 디자인팀 제작 중이다 — 없으면 빈 문자열, 프론트가 플레이스홀더를 깐다."""
    monkeypatch.setattr(seed_module, "STORY_IMAGE_DIR", tmp_path)
    assert page_image_path(PAGED_SLUG, 3) == ""

    # 파일을 놓으면 그 즉시 경로가 채워진다(파일 존재가 유일한 판단 기준).
    (tmp_path / PAGED_SLUG).mkdir()
    (tmp_path / PAGED_SLUG / "p3.jpg").write_bytes(b"\xff\xd8\xff")
    assert page_image_path(PAGED_SLUG, 3) == f"/static/story/{PAGED_SLUG}/p3.jpg"
    # 다른 쪽까지 덩달아 채워지면 안 된다.
    assert page_image_path(PAGED_SLUG, 4) == ""


def test_page_audio_is_empty_when_file_missing(monkeypatch, tmp_path):
    """음성이 없으면 빈 문자열 → 프론트가 글자 수 기반 타이머로 자동 넘김한다."""
    monkeypatch.setattr(seed_module, "AUDIO_DIR", tmp_path)
    assert page_audio_path(PAGED_SLUG, 1) == ""

    (tmp_path / PAGED_SLUG).mkdir()
    (tmp_path / PAGED_SLUG / "p1.mp3").write_bytes(b"\xff\xf3fake")
    assert page_audio_path(PAGED_SLUG, 1) == f"/static/audio/{PAGED_SLUG}/p1.mp3"


def test_page_asset_paths_are_empty_for_unknown_slug():
    assert page_image_path("", 1) == ""
    assert page_audio_path("", 1) == ""


def test_build_intro_pages_leaves_assets_empty_when_nothing_exists(monkeypatch, tmp_path):
    """자산 폴더가 통째로 비어도 텍스트만으로 페이지가 성립한다(그림·음성은 선택)."""
    monkeypatch.setattr(seed_module, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(seed_module, "STORY_IMAGE_DIR", tmp_path / "story")

    pages = build_intro_pages(PAGED_TITLE, {1: "첫 쪽.", 2: "둘째 쪽."})
    assert [p["no"] for p in pages] == [1, 2]
    for page in pages:
        assert page["image"] == ""
        assert page["audio"] == ""


# ── 실제 생성된 페이지 음성 ─────────────────────────────────────────────────
def test_generated_page_audio_files_are_wired_up():
    """생성해 커밋한 페이지 mp3 6개가 시딩 경로와 정확히 이어진다."""
    pages = _paged_story()["intro_pages"]
    slug = story_slug(PAGED_TITLE)

    for page in pages:
        path = seed_module.AUDIO_DIR / slug / f"p{page['no']}.mp3"
        assert path.is_file(), f"페이지 음성 누락: {path}"
        assert path.stat().st_size > 0
        assert page["audio"] == f"/static/audio/{slug}/p{page['no']}.mp3"

    # 통짜 요약 음성은 그대로 남는다 — 북뷰어가 없는 이야기의 폴백이자 PDF 원작 1쪽 자산.
    assert (seed_module.AUDIO_DIR / f"{slug}.mp3").is_file()


# ── (c) API ─────────────────────────────────────────────────────────────────
async def test_story_detail_includes_intro_pages(full_client: AsyncClient):
    cards = (await full_client.get("/api/stories")).json()
    card = next(c for c in cards if c["title"] == PAGED_TITLE)

    detail = (await full_client.get(f"/api/stories/{card['id']}")).json()
    assert len(detail["intro_pages"]) == EXPECTED_PAGE_COUNT
    for page in detail["intro_pages"]:
        assert set(page) == {"no", "text", "image", "audio"}
        assert page["text"]
    # 요약은 그대로 남는다 — 북뷰어가 없는 이야기의 폴백이라 지우면 안 된다.
    assert detail["intro_summary"]


async def test_story_detail_intro_pages_empty_for_other_stories(full_client: AsyncClient):
    cards = (await full_client.get("/api/stories")).json()

    for card in cards:
        if card["title"] == PAGED_TITLE:
            continue
        detail = (await full_client.get(f"/api/stories/{card['id']}")).json()
        assert detail["intro_pages"] == [], card["title"]


async def test_story_list_omits_intro_pages(full_client: AsyncClient):
    """목록 카드는 상세 전용 필드를 싣지 않는다 — 서가에서는 읽지 않는다."""
    for card in (await full_client.get("/api/stories")).json():
        assert "intro_pages" not in card


async def test_page_audio_is_served_as_static_file(full_client: AsyncClient):
    """응답 경로가 실제로 /static 마운트에서 내려온다(경로 오타 회귀 방지)."""
    cards = (await full_client.get("/api/stories")).json()
    card = next(c for c in cards if c["title"] == PAGED_TITLE)
    detail = (await full_client.get(f"/api/stories/{card['id']}")).json()

    first = detail["intro_pages"][0]
    resp = await full_client.get(first["audio"])
    assert resp.status_code == 200
    assert resp.content[:3] == b"ID3" or (
        resp.content[0] == 0xFF and (resp.content[1] & 0xE0) == 0xE0
    )
