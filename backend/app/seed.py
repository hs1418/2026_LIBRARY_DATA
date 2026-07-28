"""전래동화 10편 시딩 스크립트 — python -m app.seed.

진실 소스는 AI팀 시드 파일(AI/data/fairytale_seeds.txt) 한 곳이다. 이 모듈은 그 파일을
파싱해 Story 행으로 옮기기만 한다 — AI팀이 파일만 고치면 재시딩으로 그대로 반영된다.

시드 파일 문법:
    [STORY_n]      TITLE / EMOJI / KEYWORD / INTRO_SUMMARY 필드
    [RECOMMEND_n]  "번호. 제목 | 저자 | 출판사 | 청구기호" 5줄
    '#' 로 시작하는 줄과 빈 줄은 주석/구분선이라 무시한다.

판권기(bibliography)는 시드 파일에 발행연도·발행처가 없다. 실물 서지를 확보한
콩쥐팥쥐전(1920년대 딱지본, AI/data/kongjwi_seed.txt)만 채우고 나머지 9편은 비워 둔다.
발행연도를 지어내면 허위 서지가 인쇄물에 박히므로, 빈 값은 렌더 계층에서
"원작 : 옛이야기(구전) …" 일반 문구로 폴백한다(pdf.py original_credit).

recommend_books 는 정보나루 장애 시 폴백의 진실 소스이기도 하다
(data4library._fallback_books → Story.recommend_books 우선).
"""
import asyncio
import re
from pathlib import Path

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Story

# backend/app/seed.py → 레포 루트/AI/data/fairytale_seeds.txt
SEED_FILE = (
    Path(__file__).resolve().parent.parent.parent / "AI" / "data" / "fairytale_seeds.txt"
)

# 정적 자산 루트(backend/static) — 표지·딱지본 스캔·도입부 음성이 모두 여기 있다.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
AUDIO_DIR = STATIC_DIR / "audio"

# 제목 → ASCII slug. 파일명은 ASCII 로 고정한다(URL·파일시스템 안전).
# 표지 이미지와 도입부 음성이 이 매핑 하나를 공유한다 — 자산 종류마다 매핑을 복제하면
# 한쪽만 고쳐져 파일명이 갈라진다. 자산별 예외는 아래 제외 목록으로만 표현한다.
STORY_SLUGS: dict[str, str] = {
    "콩쥐팥쥐전": "kongjwi",
    "흥부놀부전": "heungbu",
    "해님달님전": "haenim",
    "혹부리 영감": "hokburi",
    "금도끼 은도끼": "geumdokki",
    "별주부전": "byeoljubu",
    "은혜 갚는 까치": "kkachi",
    "선녀와 나무꾼": "seonnyeo",
    "심청전": "simcheong",
    "단군신화 (곰과 호랑이)": "dangun",
}

# 서가에서 아예 빼는 이야기. 혹부리 영감 표지는 그림 현판이 "흑부리 영감"으로 잘못
# 그려져 있다(2026-07-27 확인). 이모지 표지로 폴백하면 10편 중 한 칸만 그림이 없어
# 서가가 미완성으로 보이므로, 표지가 재생성될 때까지 이야기째 숨긴다 —
# 9편이 완결된 편이 10편 중 하나가 빈 것보다 완성도 면에서 낫다.
# 시드 파일·음성·표지 파일은 모두 보존한다(집합에서 제목만 빼면 즉시 되살아난다).
EXCLUDED_TITLES: frozenset[str] = frozenset({"혹부리 영감"})

# 표지 그림에서만 제외되는 이야기(현재 없음 — 위 EXCLUDED_TITLES 로 통합).
COVER_EXCLUDED_TITLES: frozenset[str] = frozenset()

# 표지 이미지 slug — 시드 파일에 없는 제목이면 빈 문자열이 들어가고 이모지 표지로 폴백한다.
COVER_SLUGS: dict[str, str] = {
    title: slug
    for title, slug in STORY_SLUGS.items()
    if title not in COVER_EXCLUDED_TITLES
}

# 딱지본 스캔을 확보한 이야기만 화면에 액자를 띄운다(없으면 프론트가 영역째 숨긴다).
INTRO_IMAGES: dict[str, str] = {
    "콩쥐팥쥐전": "/static/scans/kongjwi_intro.jpg",
}

# 실물 서지가 확인된 이야기만. 나머지는 의도적으로 비운다(발행연도 창작 금지).
BIBLIOGRAPHIES: dict[str, dict] = {
    "콩쥐팥쥐전": {
        "title": "콩쥐팥쥐전",
        "isbn": "9788939502148",
        "publisher": "영창서관 (원작 출판) / 보림 (현대 재해석)",
        "year": "1920s (딱지본 원전) / 2018 (표준 서지)",
        "reg_no": "K2026-LIB-10492",
        "source": "국립중앙도서관 국가서지",
    },
}

_SECTION_RE = re.compile(r"^\[(STORY|RECOMMEND)_(\d+)\]$")
_FIELD_RE = re.compile(r"^(TITLE|EMOJI|KEYWORD|INTRO_SUMMARY)\s*:\s*(.*)$")
_BOOK_RE = re.compile(r"^\d+\.\s*(.+)$")


def _parse_book(line: str) -> dict:
    """'제목 | 저자 | 출판사 | 청구기호' → dict. 뒤쪽 칸이 비어도 빈 문자열로 채운다."""
    cells = [cell.strip() for cell in line.split("|")]
    cells += [""] * (4 - len(cells))
    return {
        "title": cells[0],
        "author": cells[1],
        "publisher": cells[2],
        "call_number": cells[3],
    }


def story_slug(title: str) -> str:
    """제목 → ASCII slug. 매핑에 없으면 빈 문자열."""
    return STORY_SLUGS.get(title, "")


def cover_path(title: str) -> str:
    """제목 → 표지 이미지 URL. 매핑에 없으면 빈 문자열(이모지 폴백)."""
    slug = COVER_SLUGS.get(title, "")
    return f"/static/covers/{slug}.jpg" if slug else ""


def audio_path(title: str) -> str:
    """제목 → 도입부 요약 음성 URL. 파일이 실제로 있을 때만 채운다.

    음성은 런타임에 만들지 않고 개발 시점에 미리 생성해 커밋한다
    (scripts/generate_intro_audio.py). 그래서 시딩 시점에 파일 존재를 확인할 수 있고,
    없으면 빈 문자열 → 프론트가 재생 버튼째 숨긴다(표지·딱지본 스캔과 같은 폴백 규칙).
    """
    slug = story_slug(title)
    if not slug:
        return ""
    return f"/static/audio/{slug}.mp3" if (AUDIO_DIR / f"{slug}.mp3").is_file() else ""


def parse_seed_file(path: Path | None = None) -> list[dict]:
    """시드 파일 → Story(**dict) 로 바로 넘길 수 있는 dict 목록(파일 등장 순서).

    [STORY_n] 과 [RECOMMEND_n] 은 같은 번호로 짝지어진다 — 파일에서 떨어져 있어도 된다.
    """
    text = (path or SEED_FILE).read_text(encoding="utf-8")

    fields: dict[int, dict[str, str]] = {}
    books: dict[int, list[dict]] = {}
    order: list[int] = []
    current: tuple[str, int] | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        section = _SECTION_RE.match(line)
        if section:
            kind, number = section.group(1), int(section.group(2))
            current = (kind, number)
            if kind == "STORY" and number not in fields:
                fields[number] = {}
                order.append(number)
            elif kind == "RECOMMEND":
                books.setdefault(number, [])
            continue

        if current is None:
            continue

        kind, number = current
        if kind == "STORY":
            field = _FIELD_RE.match(line)
            if field:
                fields[number][field.group(1)] = field.group(2).strip()
        else:
            book = _BOOK_RE.match(line)
            if book:
                books[number].append(_parse_book(book.group(1)))

    stories: list[dict] = []
    for number in order:
        entry = fields[number]
        title = entry.get("TITLE", "")
        if not title:
            raise ValueError(f"[STORY_{number}] 에 TITLE 이 없다: {SEED_FILE}")

        # 표지 결함 등으로 보류된 이야기는 서가에 올리지 않는다(파일은 보존).
        if title in EXCLUDED_TITLES:
            continue

        keywords = [kw.strip() for kw in entry.get("KEYWORD", "").split(",") if kw.strip()]
        stories.append(
            {
                "title": title,
                "emoji": entry.get("EMOJI", ""),
                # 서가 카드에 찍히는 대표 키워드는 첫 번째 것.
                "keyword": keywords[0] if keywords else "",
                "intro_summary": entry.get("INTRO_SUMMARY", ""),
                "intro_image": INTRO_IMAGES.get(title, ""),
                "intro_audio": audio_path(title),
                "cover_image": cover_path(title),
                "bibliography": BIBLIOGRAPHIES.get(title, {}),
                "fixed_keywords": keywords,
                "recommend_books": books.get(number, []),
            }
        )
    return stories


async def seed() -> None:
    """시드 파일의 이야기를 DB 에 넣는다. 이야기별 개별 존재 체크라 부분 시딩도 메꾼다."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    stories = parse_seed_file()

    async with SessionLocal() as db:
        result = await db.execute(select(Story.title))
        existing = set(result.scalars().all())

        added = [Story(**data) for data in stories if data["title"] not in existing]
        if not added:
            print(f"이미 시딩됨: {len(stories)}편 전부")
            return

        db.add_all(added)
        await db.commit()
        print(f"시딩 완료: {len(added)}편 추가 ({', '.join(s.title for s in added)})")


if __name__ == "__main__":
    asyncio.run(seed())
