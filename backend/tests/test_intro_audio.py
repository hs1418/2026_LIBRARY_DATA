"""도입부 요약 음성(intro_audio) 회귀 테스트 — 전부 로컬 파일 검사 (실키·네트워크 불필요).

mp3 는 개발 시점에 만들어 커밋한 정적 자산이다(scripts/generate_intro_audio.py).
런타임에 edge-tts 를 호출하지 않으므로 여기서 검증할 것은 "파일이 있는지"와
"시딩·API 가 그 사실을 정확히 반영하는지" 두 가지다.

검증:
(a) 10편 mp3 가 모두 있고 파일명이 slug 규칙(ASCII)을 지킨다 + 유효한 mp3 헤더
(b) 시드는 파일이 실제로 존재하는 이야기만 intro_audio 를 채운다
(c) GET /api/stories/{id} 응답에 intro_audio 가 들어간다(목록에는 없다)
(d) 파일이 없는 이야기는 빈 문자열 → 프론트가 재생 버튼째 숨긴다
"""
import re
from pathlib import Path

from httpx import AsyncClient

from app import seed as seed_module
from app.seed import AUDIO_DIR, STORY_SLUGS, audio_path, parse_seed_file, story_slug

# 앱 코드(app/)는 edge-tts 를 import 하지 않는다 — 런타임 TTS 호출 금지의 회귀 방지 대상.
APP_DIR = Path(seed_module.__file__).resolve().parent


def _is_mp3(data: bytes) -> bool:
    """ID3 태그 또는 MPEG 프레임 동기워드(0xFFEx)로 시작하면 mp3 로 본다."""
    return data.startswith(b"ID3") or (
        len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
    )


# ── (a) 자산 ────────────────────────────────────────────────────────────────
def test_all_ten_stories_have_intro_audio_files():
    titles = [story["title"] for story in parse_seed_file()]
    assert len(titles) == 10

    for title in titles:
        slug = story_slug(title)
        assert slug, f"STORY_SLUGS 에 slug 가 없다: {title}"
        path = AUDIO_DIR / f"{slug}.mp3"
        assert path.is_file(), f"음성 파일 누락: {path.name} ({title})"
        assert path.stat().st_size > 0, path.name
        assert _is_mp3(path.read_bytes()[:4]), f"mp3 헤더가 아니다: {path.name}"


def test_audio_files_are_ascii_slugs():
    """파일명은 ASCII slug 여야 한다(URL·파일시스템 안전) — 표지와 같은 규칙."""
    for slug in STORY_SLUGS.values():
        name = f"{slug}.mp3"
        assert name.isascii()
        assert Path(name).stem.replace("_", "").isalnum()


def test_cover_slugs_are_derived_from_the_single_slug_map():
    """표지 slug 는 공통 매핑에서 파생된다 — 매핑 두 개가 갈라지는 사고 방지."""
    assert set(seed_module.COVER_SLUGS) <= set(STORY_SLUGS)
    for title, slug in seed_module.COVER_SLUGS.items():
        assert slug == STORY_SLUGS[title]
    # 표지에서 제외된 이야기도 음성 slug 는 유지된다(표지 유무와 음성은 무관).
    for title in seed_module.COVER_EXCLUDED_TITLES:
        assert title not in seed_module.COVER_SLUGS
        assert story_slug(title)


def test_app_code_never_imports_edge_tts():
    """런타임 TTS 호출 금지(ADR-0004) — 생성은 scripts/ 전용 도구에서만 한다.

    주석 언급은 허용하고 import 문만 잡는다(문구가 바뀌어도 깨지지 않게).
    """
    import_re = re.compile(r"^\s*(?:import\s+edge_tts|from\s+edge_tts\b)", re.MULTILINE)
    offenders = [
        path.name
        for path in APP_DIR.rglob("*.py")
        if import_re.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
    # requirements.txt 에도 들어가면 안 된다 — 배포 이미지에 생성 도구를 싣지 않는다.
    requirements = (APP_DIR.parent / "requirements.txt").read_text(encoding="utf-8")
    assert "edge-tts" not in requirements
    assert "edge_tts" not in requirements


# ── (b)(d) 시드 ─────────────────────────────────────────────────────────────
def test_seed_fills_intro_audio_only_for_existing_files():
    for story in parse_seed_file():
        slug = story_slug(story["title"])
        exists = bool(slug) and (AUDIO_DIR / f"{slug}.mp3").is_file()
        if exists:
            assert story["intro_audio"] == f"/static/audio/{slug}.mp3"
        else:
            assert story["intro_audio"] == ""


def test_audio_path_is_empty_when_file_missing(monkeypatch, tmp_path):
    """slug 는 있어도 파일이 없으면 빈 문자열 — 프론트가 재생 UI 를 숨긴다."""
    monkeypatch.setattr(seed_module, "AUDIO_DIR", tmp_path)
    assert audio_path("콩쥐팥쥐전") == ""

    # 파일을 놓으면 그 즉시 경로가 채워진다(파일 존재가 유일한 판단 기준).
    (tmp_path / "kongjwi.mp3").write_bytes(b"\xff\xf3fake")
    assert audio_path("콩쥐팥쥐전") == "/static/audio/kongjwi.mp3"


def test_audio_path_is_empty_for_unknown_title():
    assert audio_path("매핑에 없는 이야기") == ""


def test_seed_parser_still_builds_story_rows_with_audio_field():
    """parse_seed_file 결과가 Story(**data) 계약을 유지한다(필드 추가 회귀)."""
    from app.models import Story

    stories = [Story(**data) for data in parse_seed_file()]
    assert len(stories) == 10
    assert any(story.intro_audio for story in stories)


# ── (c) API ─────────────────────────────────────────────────────────────────
async def test_story_detail_includes_intro_audio(full_client: AsyncClient):
    stories = (await full_client.get("/api/stories")).json()
    assert len(stories) == 10

    with_audio = 0
    for card in stories:
        resp = await full_client.get(f"/api/stories/{card['id']}")
        assert resp.status_code == 200
        detail = resp.json()
        assert "intro_audio" in detail
        if detail["intro_audio"]:
            with_audio += 1
            assert detail["intro_audio"].startswith("/static/audio/")
            assert detail["intro_audio"].endswith(".mp3")
    # 10편 전부 음성이 붙어 있어야 한다(자산 누락 회귀 방지).
    assert with_audio == 10


async def test_story_list_omits_intro_audio(full_client: AsyncClient):
    """목록 카드는 상세 전용 필드를 싣지 않는다 — 서가에서는 재생하지 않는다."""
    stories = (await full_client.get("/api/stories")).json()
    for card in stories:
        assert "intro_audio" not in card


async def test_story_detail_audio_is_served_as_static_file(full_client: AsyncClient):
    """응답 경로가 실제로 /static 마운트에서 내려온다(경로 오타 회귀 방지)."""
    card = (await full_client.get("/api/stories")).json()[0]
    detail = (await full_client.get(f"/api/stories/{card['id']}")).json()

    resp = await full_client.get(detail["intro_audio"])
    assert resp.status_code == 200
    assert _is_mp3(resp.content[:4])
