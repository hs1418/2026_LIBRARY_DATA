import asyncio
import edge_tts
import os
import re

# 시드 데이터 파일 경로 (AI/data/fairytale_seeds.txt)
# 운영체제 간 경로 호환성을 위해 os.path.join 사용
SEEDS_FILE_PATH = os.path.join(os.path.dirname(__file__), "data", "fairytale_seeds.txt")

# 오디오 파일 저장 경로 (AI/audio/)
AUDIO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "audio")

# 저장 폴더가 없으면 생성
if not os.path.exists(AUDIO_OUTPUT_DIR):
    os.makedirs(AUDIO_OUTPUT_DIR)


def get_intro_summary_from_seeds(story_id: str = "STORY_1") -> str:
    """
    fairytale_seeds.txt 파일에서 이야기 ID(STORY_1 ~ STORY_10)에 해당하는 
    INTRO_SUMMARY(초반 내용 요약) 텍스트를 파싱하여 반환합니다.
    """
    default_text = "옛날 옛적 어느 마을에 마음씨 착한 아이가 살고 있었어요."
    
    # 파일 존재 확인
    possible_paths = [
        SEEDS_FILE_PATH,
        os.path.join("AI", "data", "fairytale_seeds.txt"),
        os.path.join("data", "fairytale_seeds.txt")
    ]
    
    target_path = None
    for path in possible_paths:
        if os.path.exists(path):
            target_path = path
            break

    if not target_path:
        print(f"[WARN] 시드 파일을 찾을 수 없어 기본 텍스트를 사용합니다.")
        return default_text

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 정규표현식을 사용하여 [STORY_X] 블록 내의 INTRO_SUMMARY 추출
        # re.DOTALL 옵션으로 줄바꿈 포함 탐색
        pattern = rf'\[{story_id}\].*?INTRO_SUMMARY:\s*(.*?)(?=\n\n|\n\[|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            # 줄바꿈 및 앞뒤 공백 제거 후 반환
            return match.group(1).replace('\n', ' ').strip()
            
    except Exception as e:
        print(f"[ERROR] 시드 데이터 파싱 실패: {e}")

    return default_text


async def generate_intro_audio_async(story_id: str = "STORY_1") -> str:
    """
    story_id를 받아 해당 동화의 초반 요약글을 구수한 전래동화 어조로
    TTS 오디오 파일(.mp3)을 생성하고 저장 경로를 반환합니다.
    (속도 -20%, 피치 -5Hz 설정)
    """
    
    # 1. 시드 데이터에서 텍스트 가져오기
    text = get_intro_summary_from_seeds(story_id)
    
    if not text:
        return ""

    # 2. 파일명 및 경로 설정 (예: AI/audio/intro_STORY_1.mp3)
    filename = f"intro_{story_id}.mp3"
    output_path = os.path.join(AUDIO_OUTPUT_DIR, filename)

    # 3. TTS 설정 (Microsoft Edge 무료 엔진)
    # 한국어 여성 기본 음성 사용 (속도 감속 및 피치 조율로 옛날이야기 톤 연출)
    voice = "ko-KR-SunHiNeural"
    
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate="-20%",  # 천천히 읽어 옛날 이야기 느림보 어조 연출
        pitch="-5Hz"  # 약간 낮고 차분한 톤
    )
    
    # 4. 오디오 파일 생성 및 저장
    try:
        await communicate.save(output_path)
        print(f"[INFO] [{story_id}] 초반 요약 오디오 생성 완료: {output_path}")
        return output_path
    except Exception as e:
        print(f"[ERROR] TTS 오디오 생성 실패 ({story_id}): {e}")
        return ""


def generate_intro_audio(story_id: str = "STORY_1") -> str:
    """
    동기식(Sync) 환경에서 간편하게 호출할 수 있는 래퍼 함수입니다.
    """
    return asyncio.run(generate_intro_audio_async(story_id))


# ========================================================
# 로컬 독립 테스트 및 초기 오디오 생성용 실행 코드
# ========================================================
if __name__ == "__main__":
    # 테스트 1: 콩쥐팥쥐(STORY_1) 초반 요약 음성 생성
    print("--- [테스트 1] STORY_1 오디오 생성 ---")
    result_path_1 = generate_intro_audio("STORY_1")
    
    # 테스트 2: 해님달님(STORY_3) 초반 요약 음성 생성
    print("\n--- [테스트 2] STORY_3 오디오 생성 ---")
    result_path_3 = generate_intro_audio("STORY_3")

    print("\n--- 생성 완료 ---")
    print(f"STORY_1 결과: {result_path_1}")
    print(f"STORY_3 결과: {result_path_3}")
    
    # 팁: 이 파일을 그대로 실행하면 AI/audio/ 폴더에 10선 전체 오디오를 미리 만들어둘 수도 있습니다.
    # print("\n--- [초기화] 10선 전체 오디오 사전 생성 ---")
    # for i in range(1, 11):
    #     generate_intro_audio(f"STORY_{i}")
