import json
import html
import os
from groq import Groq

# Groq 클라이언트 세팅 (환경변수 사용)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def generate_story_and_keywords(intro_summary: str, child_speech_accumulated: str) -> dict:
    """
    아동 구술 데이터를 기반으로 Llama 3.1을 호출하여
    페이지 분할 동화(한/영) 및 추천 키워드를 JSON으로 반환합니다.
    """
    client = Groq(api_key=GROQ_API_KEY)

    # v1.2 고도화된 시스템 프롬프트 (명칭 보존 및 정확한 영문 고유명사 지침 추가)
    system_prompt = """
    당신은 대한민국 최고의 아동용 전래동화 전문 작가이자 번역가입니다.
    전달받은 [원작 앞부분 요약]과 [아동의 구술 입력]을 유기적으로 이어 붙여 따뜻한 결말을 완성하세요.

    [동화체 작성 지침 (아이 말투 살리기)]:
    1. 고유명사 유지: 등장인물이나 동물 이름(예: 콩쥐->Kongjwi, 두꺼비->Toad)을 환각(Hallucination)으로 변형하거나 오역하지 마세요.
2. 문체: 아동이 친근감을 느낄 수 있는 높임 동화체(~했지요, ~했답니다, ~했지 뭐예요)를 사용하세요.
    3. 각색: 아동의 구술 데이터가 파편화되어 있거나 짧더라도, 문맥을 자연스럽게 보완하여 동화의 서사 구조를 완성하세요.
    4. 분량 및 페이지: 전체 결말을 반드시 3~5개의 페이지("pages")로 분할하세요. 각 페이지는 그림책 한 면에 들어갈 1~2문장 내외로 구성하세요.

    [JSON 파싱 가드레일 (엄격 적용)]:
    1. 출력 형태: 오직 순수한 JSON 객체 하나만 반환하세요.
    2. 절대 금지 사항: 인사말, 설명, 서론, 결론, Markdown 코드 블록(```json)을 단 한 글자도 출력하지 마세요.
    3. 스키마 준수: Key 이름("pages", "no", "ko", "en", "keywords")을 절대 변경하지 마세요.
    """

    user_prompt = f"""
    [동화 앞부분 요약]: {intro_summary}
    [아이의 구술 입력]: {child_speech_accumulated}

    [JSON 반환 포맷 예시]:
    {{
      "pages": [
        {{ "no": 1, "ko": "한글 문장 1", "en": "English sentence 1" }},
        {{ "no": 2, "ko": "한글 문장 2", "en": "English sentence 2" }}
      ],
      "keywords": ["키워드1", "키워드2"]
    }}
    """

    # Groq Llama 3.1 호출
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        model="llama-3.1-8b-instant",
        response_format={"type": "json_object"},
        temperature=0.5  # 고유명사 변형 방지를 위해 창의성 수치를 0.7 -> 0.5로 안정화
    )

    # 응답 데이터 파싱 및 XSS 방어 처리
    raw_content = response.choices[0].message.content
    data = json.loads(raw_content)

    # XSS 방어를 위한 html.escape 처리 (NFR-5 준수)
    for page in data.get("pages", []):
        page["ko"] = html.escape(page.get("ko", ""))
        page["en"] = html.escape(page.get("en", ""))

    return data
