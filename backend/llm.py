import json
import html
import os
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def generate_story_and_keywords(intro_summary: str, child_speech_accumulated: str) -> dict:
    """
    아동 구술 데이터를 기반으로 Groq Llama 3.1 70B를 호출하여
    아이의 구술 지점부터 바로 이어지는 동화(한/영) 및 추천 키워드를 JSON으로 반환합니다.
    """
    client = Groq(api_key=GROQ_API_KEY)

    # v1.3 이어쓰기 강제 & 70B 최적화 프롬프트
    system_prompt = """
    당신은 대한민국 최고의 아동용 전래동화 전문 작가이자 번역가입니다.

    [핵심 법칙: 절대적 이어쓰기 (Strong Continuation)]:
    1. [원작 앞부분 요약]은 단지 상황 이해를 위한 배경지식일 뿐입니다. 이미 책 앞쪽에 인쇄되어 있으므로 본문에서 절대 다시 요약하거나 반복하지 마세요.
    2. 생성되는 첫 번째 페이지("no": 1)는 반드시 [아동의 구술 입력]이 시작되는 내용부터 곧바로 이어져야 합니다.
    3. 아동의 구술 내용을 중심 서사로 삼아 자연스럽고 따뜻한 결말까지 완결하세요.

    [등장인물 고유명사 번역 지침 (오역 엄금)]:
    - 콩쥐 -> Kongjwi
    - 팥쥐 -> Patjwi (절대 Rabbit, Red Bean 등 오역 금지)
    - 두꺼비 -> Toad (절대 Rabbit 오역 금지)
    - 오타 환각 금지: 등장인물 이름을 '콤쥐', '콰콰이' 등으로 변형하지 마세요.

    [동화체 작성 지침]:
    1. 문체: 아동이 친근감을 느낄 수 있는 높임 동화체(~했지요, ~했답니다, ~했지 뭐예요)를 사용하세요.
    2. 분량 및 페이지: 전체 결말을 반드시 3~5개의 페이지("pages")로 분할하세요. 각 페이지는 그림책 한 면에 들어갈 1~2문장 내외로 구성하세요.

    [JSON 파싱 가드레일 (엄격 적용)]:
    1. 출력 형태: 오직 순수한 JSON 객체 하나만 반환하세요.
    2. 절대 금지 사항: 인사말, 설명, 서론, 결론, Markdown 코드 블록(```json)을 단 한 글자도 출력하지 마세요.
    3. 스키마 준수: Key 이름("pages", "no", "ko", "en", "keywords")을 절대 변경하지 마세요.
    """

    user_prompt = f"""
    [배경 참고용 - 원작 앞부분 요약 (절대 다시 쓰지 말 것)]: {intro_summary}
    [아이의 구술 입력 (여기서부터 1페이지 시작)]: {child_speech_accumulated}

    [JSON 반환 포맷 예시]:
    {{
      "pages": [
        {{ "no": 1, "ko": "한글 문장 1", "en": "English sentence 1" }},
        {{ "no": 2, "ko": "한글 문장 2", "en": "English sentence 2" }}
      ],
      "keywords": ["키워드1", "키워드2"]
    }}
    """

    # Groq Llama 3.1 70B 모델로 업그레이드 (고유명사 정확도 및 맥락 이해도 대폭 향상)
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        model="llama-3.1-70b-versatile",
        response_format={"type": "json_object"},
        temperature=0.3  # 오역 및 환각 방지를 위해 창의성을 안정적인 0.3으로 설정
    )

    raw_content = response.choices[0].message.content
    data = json.loads(raw_content)

    for page in data.get("pages", []):
        page["ko"] = html.escape(page.get("ko", ""))
        page["en"] = html.escape(page.get("en", ""))

    return data
