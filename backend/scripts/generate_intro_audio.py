"""도입부 요약 음성(mp3) 사전 생성 도구 — backend/ 에서 `python -m scripts.generate_intro_audio`.

런타임에 TTS 를 호출하지 않는다(ADR-0004 정신). 이유 세 가지:
  1. INTRO_SUMMARY 는 시드에 박힌 고정 텍스트라 매번 합성할 이유가 없다
  2. 배포본(Render 무료 플랜) 디스크는 재기동마다 초기화된다 — 런타임 생성물은 사라진다
  3. 워크숍 현장 인터넷이 불안정하다 — 외부 TTS 가 재생 실패 지점이 되면 안 된다
그래서 개발 시점에 10편 mp3 를 만들어 backend/static/audio/ 에 커밋하고, 서비스는 그
파일만 정적 배포한다. 앱 코드(app/) 어디에도 edge-tts import 는 없다.

edge-tts 는 이 스크립트 전용 생성 도구라 requirements.txt 에 넣지 않는다
(필요할 때만 `pip install edge-tts`).

음성 톤 설계(voice / rate / pitch)는 AI담당자 소관이다. 아래 상수는 AI팀 산출물
AI/tts_generator.py 의 값을 그대로 옮긴 것이며, 변경 시 협의할 것.

사용법:
    python -m scripts.generate_intro_audio           # 없는 것만 생성
    python -m scripts.generate_intro_audio --force   # 전부 재생성
"""
import argparse
import asyncio
from pathlib import Path

from app.seed import AUDIO_DIR, parse_seed_file, story_slug

try:
    import edge_tts
except ModuleNotFoundError:  # 생성 전용 도구 — 서비스 실행에는 필요 없다.
    edge_tts = None

# --- AI/tts_generator.py 원본 값 (AI담당자 소관 — 변경 시 협의) ---------------
# 한국어 여성 기본 음성 + 감속/저피치로 전래동화 성우 톤을 낸다.
VOICE = "ko-KR-SunHiNeural"
RATE = "-20%"  # 천천히 읽어 옛날이야기 어조 연출
PITCH = "-5Hz"  # 약간 낮고 차분한 톤
# ---------------------------------------------------------------------------


async def synthesize(text: str, out_path: Path) -> None:
    """텍스트 → mp3. 부분 파일이 남지 않게 임시 파일에 받고 마지막에 옮긴다.

    중간에 끊긴 파일이 남으면 시딩이 그것을 정상 음성으로 오인해 채워 버린다.
    """
    communicate = edge_tts.Communicate(text=text, voice=VOICE, rate=RATE, pitch=PITCH)
    tmp_path = out_path.with_name(out_path.name + ".part")
    try:
        await communicate.save(str(tmp_path))
        tmp_path.replace(out_path)
    finally:
        tmp_path.unlink(missing_ok=True)


async def generate_all(force: bool) -> int:
    """시드 10편의 INTRO_SUMMARY 를 음성으로 만든다. 반환값은 프로세스 종료 코드."""
    if edge_tts is None:
        print("[FAIL] edge-tts 가 없다. `pip install edge-tts` 후 다시 실행할 것.")
        return 2

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    stories = parse_seed_file()
    print(f"시드 {len(stories)}편 / 출력 폴더 {AUDIO_DIR}")
    print(f"음성 설정: voice={VOICE} rate={RATE} pitch={PITCH}\n")

    created = skipped = failed = 0
    for story in stories:
        title = story["title"]
        slug = story_slug(title)
        if not slug:
            print(f"[FAIL] slug 매핑이 없다 — app/seed.py STORY_SLUGS 에 추가할 것: {title}")
            failed += 1
            continue

        text = story["intro_summary"].strip()
        if not text:
            print(f"[FAIL] INTRO_SUMMARY 가 비었다 — 시드 파일 확인: {title}")
            failed += 1
            continue

        out_path = AUDIO_DIR / f"{slug}.mp3"
        if out_path.is_file() and not force:
            print(f"[SKIP] 이미 있음  {out_path.name} ({out_path.stat().st_size:,} bytes)")
            skipped += 1
            continue

        print(f"[GEN ] {title} ({len(text)}자) → {out_path.name}")
        try:
            await synthesize(text, out_path)
        except Exception as exc:  # noqa: BLE001 - 한 편 실패가 나머지를 막지 않게 한다
            print(f"[FAIL] {title}: {type(exc).__name__}: {exc}")
            failed += 1
            continue

        print(f"[ OK ] {out_path.name} ({out_path.stat().st_size:,} bytes)")
        created += 1

    total = sum(p.stat().st_size for p in AUDIO_DIR.glob("*.mp3"))
    print(f"\n생성 {created} / 건너뜀 {skipped} / 실패 {failed}")
    print(f"현재 {AUDIO_DIR.name}/ 총 용량: {total:,} bytes")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="도입부 요약 음성(mp3) 사전 생성")
    parser.add_argument(
        "--force", action="store_true", help="이미 있는 파일도 다시 생성한다"
    )
    args = parser.parse_args()
    return asyncio.run(generate_all(args.force))


if __name__ == "__main__":
    raise SystemExit(main())
