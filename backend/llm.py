# 1. Groq 전용 공식 호환 라이브러리를 설치합니다.
!pip install -q -U groq requests

import json
from groq import Groq

# 1. Groq 클라이언트 세팅 (기존 API 키 사용)
# 실제 운영 시에는 os.getenv("GROQ_API_KEY")로 로드
GROQ_API_KEY = "GroQ_API_KEY"
client = Groq(api_key=GROQ_API_KEY)

def test_story_generation():
    intro_summary = "콩쥐가 눈물을 흘리던 그 순간, 어디선가 커다란 두꺼비 한 마리가 나타나 깨진 독의 구멍을 온몸으로 막아주었습니다. 이제 드디어 마을에서 열리는 신나는 잔치에 가고 싶어 하는데..."
    child_speech_accumulated = "두꺼비가 황금 신발을 줬어요. 잔치에 가서 왕자님을 만났어요."
    
    prompt = f"""
    당신은 아동용 전래동화 작가입니다.
    [동화 앞부분] 뒤에 이어질 결말을 [아이의 구술 입력] 조각을 바탕으로 완결된 동화로 작성하세요.

    [동화 앞부분]: {intro_summary}
    [아이의 구술 입력]: {child_speech_accumulated}

    [규칙]:
    1. 반드시 아래의 JSON 포맷 예시로만 응답하세요. Markdown 블록(```json)을 사용하지 마세요.
    2. 전체 스토리는 3~5개의 페이지("pages")로 분할하세요.
    3. "keywords" 배열에는 도서관 정보나루 연관 도서 검색에 사용할 키워드(예: 두꺼비, 왕자님)를 2~3개 추출하세요.

    [JSON 반환 포맷 예시]:
    {{
      "pages": [
        {{ "no": 1, "ko": "한글 문장 1", "en": "English sentence 1" }},
        {{ "no": 2, "ko": "한글 문장 2", "en": "English sentence 2" }}
      ],
      "keywords": ["두꺼비", "잔치"]
    }}
    """

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        response_format={"type": "json_object"}
    )
    
    # 결과 확인
    result = json.loads(chat_completion.choices[0].message.content)
    print("✅ Groq Llama 3.1 응답 성공!")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

if __name__ == "__main__":
    test_story_generation()
