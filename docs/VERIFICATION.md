# 시스템 검증 기록

배포본(https://two026-library.onrender.com)에서 실제로 확인한 결과를 남긴다. 원고·발표에 쓰는 수치는 여기서 인용하고, 로컬에서만 확인한 것과 배포본에서 확인한 것을 구분한다.

---

## 2026-07-28 — 골든 패스 전 구간 (배포본)

전래동화 10편·표지·TTS가 모두 배포된 뒤 처음으로 배포본에서 끝까지 관통시킨 회차. Docker 런타임, Render 무료 티어(512MB RAM / 0.1 CPU), 싱가포르 리전.

| # | 검증 항목 | 결과 | 비고 |
|---|---|---|---|
| ① | 서가 목록 `GET /api/stories` | 200 · 10편 · 표지 9개 | 첫 요청 82초 (콜드스타트) |
| ② | 이야기 상세 `GET /api/stories/{id}` | 200 | `intro_audio` 경로 정상 |
| ③ | 음성 파일 `/static/audio/heungbu.mp3` | 200 · `audio/mpeg` · 78KB | |
| ④ | 표지 이미지 `/static/covers/heungbu.jpg` | 200 · `image/jpeg` · 590KB | |
| ⑤ | **동화 생성** (Llama 3.3-70B) | 200 · **2.0초** · 5페이지 | 배포본 첫 70B 실호출 |
| ⑥ | **PDF 생성** (표지 base64 인라인) | 200 · **13.1초** · 719KB · 4면 297×210mm | 512MB RAM 에서 Chromium 정상 |
| ⑦ | **추천** (정보나루 실호출) | 200 · 0.8초 · `fallback: false` · 5권 | 폴백 아닌 실제 API 응답 |
| ⑧ | 오프라인 폴백 `sessions/demo/pdf` | 200 · 114KB | ADR-0004 3계층 |

**PDF 내용 검증**: 엔티티 리터럴 0건(ADR-0008 회귀 없음), 1면 왼쪽 = 판권기(`흥부놀부전 (창작본)`) — 중철 배치 정상, 표지 이미지 임베드 1건.

**프롬프트 v1.3 효과 확인**: 아이 구술 `"제비가 박씨를 물어다 줬어! …"` → 생성 1페이지가 그 문장에서 바로 시작하고 2페이지부터 이어짐. 이전 8B 모델의 최대 결함(원작 앞부분 재요약)이 해소됐다.

### 이 회차에서 발견해 고친 것

1. **배포본이 옛 데이터로 돌던 문제** — `Dockerfile`이 `AI/data/`를 복사하지 않아 시드 파일이 이미지에 없었다. 서가에 1편만 보이는 증상으로만 드러나 원인 파악이 늦었다. → `COPY AI/data/` 추가 + bootstrap이 시딩 결과(편수·제목)를 로그로 출력하게 함.
2. **`StoryDetail` 스키마에 `cover_image` 누락** — 목록에는 있고 상세에는 없었다. 화면 동작에는 영향이 없었지만(목록에서 표지를 받으므로) 계약 불일치였다. → 추가.

### 알려진 한계

- **콜드스타트 82초** — 무료 티어가 15분 유휴 후 슬립. 녹화·심사 확인 직전에 한 번 접속해 깨워야 한다.
- **PDF 13초** (로컬 1.6초) — 0.1 CPU 에서 Chromium 렌더 비용. 워크숍은 로컬 실행이 원칙이라 실사용 영향은 없다.
- **세션은 재기동 시 소실** — DB가 `/tmp` 임시 SQLite(ADR-0003). 검증 중 세션 404 를 만났고, 새 세션을 만들어 이어서 확인했다. 배포본은 제출 링크·녹화용이라 의도된 설계다.
- **다른 이야기 인물 혼입** — 흥부놀부전 생성에 `콩쥐`가 등장. 70B 로 올려 오역은 줄었으나 인물 혼입은 남아 있다(프롬프트 튜닝 영역).

---

## 로컬 검증 (참고 수치)

워크숍 실제 운영 환경은 로컬 실행이다(ADR-0003).

| 항목 | 로컬 | 배포본 |
|---|---|---|
| 동화 생성 | 1.6초 | 2.0초 |
| PDF 생성 | 1.6초 | 13.1초 |
| 추천 | 0.4초 | 0.8초 |

**PDF 제본 구조**: A4 가로 297×210mm, 중철(saddle-stitch) 배치 — 8쪽 기준 `1면[8|1] 2면[2|7] 3면[6|3] 4면[4|5]`. 4·8·12쪽에서 표지는 항상 1면 오른쪽, 판권기는 1면 왼쪽으로 고정됨을 단위 테스트로 확인.

**도입부 음성**: 10편 사전 생성, 총 848KB / 144.7초 (MPEG-2 Layer III, 24kHz, 48kbps). 브라우저 실측 — 재생·일시정지 토글, 화면 이탈 시 정지 + 위치 초기화, 콘솔 에러 0.

**테스트**: 57건 (ruff 클린). CI(GitHub Actions)에서 ruff · pytest · Chromium 실렌더 · gitleaks · pip-audit 통과.

---

## 검증 방법 재현

```bash
# 로컬
cd backend
.venv/Scripts/python -m pytest tests -q          # 57 passed
.venv/Scripts/python -m app.bootstrap            # 시딩 결과 로그 확인
.venv/Scripts/python -m uvicorn app.main:app     # http://127.0.0.1:8000

# 배포본 (콜드스타트 대비 타임아웃 넉넉히)
U=https://two026-library.onrender.com
curl -s -m 150 "$U/api/stories"
curl -s -X POST "$U/api/stories/2/generate" -H "Content-Type: application/json" \
     -d '{"lang":"ko","child_speech":"..."}'
curl -s -X POST "$U/api/sessions/{id}/pdf" -H "Content-Type: application/json" \
     -d '{"author_name":"..."}' -o out.pdf
```
