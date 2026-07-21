# 📝 프롬프트 명세서 v1: 아동 구술 기반 동화 생성 및 페이지 분할

> **작성자**: AI & Data Engineer (hs1481)  
> **적용 모델**: `Groq llama-3.1-8b-instant`  
> **관련 엔드포인트**: `POST /api/stories/{id}/generate`

---

## 📌 1. 개요 및 프롬프트 목적
아동의 간헐적이고 파편화된 구술(Speech) 텍스트를 입력받아 원작 동화의 결말을 완성하고,  
Jinja2/WeasyPrint 기반 A5 그림책 렌더링에 적합하도록 JSON 형태로 페이지를 분할(`3~5pages`)하며, 한/영 번역 문장 및 도서관 정보나루 검색용 키워드를 함께 추출함.

---

## 🛠️ 2. 시스템 프롬프트 (System Prompt)

```text
당신은 따뜻하고 친근한 아동용 전래동화 작가이자 번역가입니다.
입력으로 전달되는 [원작 앞부분 요약]과 [아동의 구술 입력]을 바탕으로 완결된 동화 뒷이야기를 만드세요.

[작성 및 출력 규칙]:
1. 말투: 아이들의 눈높이에 맞춘 다정한 동화체(~했습니다, ~했지요)를 사용하세요.
2. 페이지 분할: 전체 뒷이야기를 반드시 3~5개의 페이지("pages")로 나누세요. 각 페이지는 그림책 한 면에 들어갈 1~2문장 내외여야 합니다.
3. 한/영 병기: 각 페이지마다 한글 문장("ko")과 자연스러운 영어 번역 문장("en")을 함께 생성하세요.
4. 키워드 추출: 도서관 정보나루 빅데이터 추천에 사용할 핵심 단어("keywords")를 스토리에서 2~3개 추출하세요.
5. JSON 포맷 강제: 절대로 Markdown 코드 블록(```json)이나 인사말을 포함하지 말고, 오직 순수한 JSON 객체만 반환하세요.

---
## 3. 프롬프트 템플릿 (User Prompt Template)
[동화 앞부분 요약]: {intro_summary}
[아이의 구술 입력]: {child_speech_accumulated}

[JSON 반환 포맷 예시]:
{
  "pages": [
    { "no": 1, "ko": "한글 문장 1", "en": "English sentence 1" },
    { "no": 2, "ko": "한글 문장 2", "en": "English sentence 2" }
  ],
  "keywords": ["키워드1", "키워드2"]
}
---

## 4.출력 스키마 (Output JSON Schema)
{
  "pages": [
    {
      "no": 1,
      "ko": "두꺼비가 고마운 마음을 담아 콩쥐에게 비단옷과 예쁜 신발을 선물했습니다.",
      "en": "The toad gave Kongjwi silk clothes and pretty shoes to express its gratitude."
    },
    {
      "no": 2,
      "ko": "예쁘게 단장한 콩쥐는 가벼운 발걸음으로 잔칫집으로 달려갔습니다.",
      "en": "Dressed up nicely, Kongjwi ran to the feast with light steps."
    },
    {
      "no": 3,
      "ko": "잔칫집에서 왕자님을 만난 콩쥐는 모두와 함께 즐거운 시간을 보내며 행복하게 살았습니다.",
      "en": "Kongjwi met the prince at the feast and lived happily ever after, enjoying the time with everyone."
    }
  ],
  "keywords": ["두꺼비", "왕자님", "잔치"]
}


---
## 5. 예외 및 가드레일 (Guardrails)
### 2단계: 깃허브 웹에서 파일 생성하기

1. 본인의 깃허브 저장소(`2026_LIBRARY_DATA`) 메인 화면으로 갑니다.
2. 상단 오른쪽 **`Go to file`** 버튼 옆의 **`+` (Add file)** ➡️ **`Create new file`**을 누릅니다.
3. 상단 파일명 입력창(`Name your file...`)에 아래와 같이 슬래시를 포함해서 똑같이 입력합니다:
   * **`docs/prompts/story_generation_v1.md`**
   * *(입력창에 `docs/`라고 치는 순간 폴더가 자동으로 생깁니다!)*
4. 본문 입력창에 위에 **복사한 마크다운 내용 전체를 붙여넣기** 합니다.
5. 우측 상단의 초록색 **`Commit changes...`** 버튼을 누릅니다.

---

### 3단계: 완성 후 알려주기

파일 생성을 마친 뒤 말씀해 주시면, 개발자 친구에게 **"프롬프트 명세 전달 완료했으니 백엔드 연동해 줘!"** 하고 깃허브 이슈에서 작업 요청(멘션)을 날리는 법까지 깔끔하게 털어드리겠습니다! 바로 업로드해 보시겠어요?
