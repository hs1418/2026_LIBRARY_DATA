import json
import html
import os
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def generate_story_and_keywords(intro_summary: str, child_speech_accumulated: str) -> dict:
    """
    아동 구술 데이터를 기반으로 Groq Llama 3.3 70B를 호출하여
    아이의 구술 지점부터 바로 이어지는 풍부한 동화(한/영) 및 추천 키워드를 JSON으로 반환합니다.
    """
    client = Groq(api_key=GROQ_API_KEY)

    # v1.4 분량 및 풍부한 서사 강화 + Llama 3.3 70B 최적화 프롬프트
    system_prompt = """
    당신은 대한민국 최고의 아동용 전래동화 전문 작가이자 번역가입니다.

    [핵심 법칙 1: 절대적 이어쓰기 (Strong Continuation)]:
    1. [원작 앞부분 요약]은 단지 상황 이해를 위한 배경지식입니다. 본문에서 절대 다시 요약하거나 반복하지 마세요.
    2. 생성되는 첫 번째 페이지("no": 1)는 반드시 [아동의 구술 입력]이 시작되는 내용부터 곧바로 이어져야 합니다.
    3. 아동의 구술 내용을 중심 서사로 삼아 자연스럽고 따뜻한 결말까지 완결하세요.

    [핵심 법칙 2: 풍부한 동화체 분량 보장 (요약 금지)]:
    1. 절대로 스토리를 1~2줄로 축약하거나 건조하게 요약하지 마세요.
    2. 등장인물의 세심한 감정 묘사, 생생한 대사, 상황 설명을 풍부하게 담아 아이들이 몰입할 수 있게 작성하세요.
    3. 전체 결말은 3~5개의 페이지("pages")로 나눌 것.
    4. 각 페이지("ko")는 단문 1줄이 아닌, **최소 2~3문장 이상**의 완성도 높은 동화책 문단으로 구성하세요.

    [등장인물 고유명사 번역 지침 (오역 엄금)]:
    - 콩쥐 -> Kongjwi
    - 팥쥐 -> Patjwi (절대 Rabbit, Red Bean 등 오역 금지)
    - 두꺼비 -> Toad (절대 Rabbit 오역 금지)
    - 오타 환각 금지: 등장인물 이름을 '콤쥐', '콰콰이' 등으로 변형하지 마세요.

    [동화체 및 번역 지침]:
    1. 문체: 아동이 친근감을 느낄 수 있는 높임 동화체(~했지요, ~했답니다, ~했지 뭐예요)를 사용하세요.
    2. 영문 번역("en"): 한글 원문의 따뜻한 어조와 감정 표현을 살려 자연스러운 어린이 동화책 스타일 영어로 번역하세요.

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
        {{ 
          "no": 1, 
          "ko": "콩쥐는 눈물을 흘리며 밑빠진 독을 바라보았어요. '어쩌면 좋지? 물이 계속 새어나가잖아.' 그때 바위 뒤에서 큼직하고 듬직한 두꺼비 한 마리가 엉금엉금 기어나왔답니다.", 
          "en": "Kongjwi looked at the broken jar with tears in her eyes. 'What should I do? The water keeps leaking out.' Just then, a big, reliable toad crawled out from behind a rock." 
        }},
        {{ 
          "no": 2, 
          "ko": "두꺼비는 넓적한 몸으로 독 구멍을 쏙 막아주며 말했어요. '콩쥐야 걱정마, 내가 도와줄게!' 콩쥐는 너무 기뻐서 두꺼비에게 몇 번이고 고마운 인사를 올렸답니다.", 
          "en": "The toad plugged the hole with its broad body and said, 'Don't worry Kongjwi, I will help you!' Kongjwi was so happy that she thanked the toad over and over again." 
        }}
      ],
      "keywords": ["콩쥐", "두꺼비", "지혜"]
    }}
    """

    # 최신 Llama 3.3 70B 모델 적용 및 안정적 파라미터 조정
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        temperature=0.5,   # 기존 0.3에서 감정/대사 표현력을 강화하기 위해 0.5로 미세 조정
        max_tokens=1500    # 스토리가 길어져도 중간에 잘리지 않도록 토큰 수 확대
    )

    raw_content = response.choices[0].message.content
    data = json.loads(raw_content)

    # HTML 특수문자 이스케이프 처리
    for page in data.get("pages", []):
        page["ko"] = html.escape(page.get("ko", ""))
        page["en"] = html.escape(page.get("en", ""))

    return data
