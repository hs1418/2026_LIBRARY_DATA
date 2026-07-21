# ADR-0001: 백엔드 API 경계·데이터 모델 확정

날짜: 2026-07-06 / 상태: accepted

## Context

팀 3명(개발자·AI담당자·디자인), 기간 2026-07-03~08-02(내부마감), 공모전·포폴용. MVP는 지원 이야기 1~2편, 로그인·다중사용자 없음, 시연 1대 안정 작동이면 됨. 스택 FastAPI+PostgreSQL+SQLAlchemy/Alembic. 워크숍 운영은 로컬 실행, Render/Railway 배포는 제출·시연영상용. 4주 안 안전 완성이 최우선 제약.

## Decision

데이터 모델은 2테이블. `Story`(사전 시딩, 거의 전 필드 정적: 제목·표지스타일·원작요약·소개영상경로·판권기·고정키워드·폴백추천도서)와 `Session`(런타임 생성, 아이 구술·생성 한글·영어만 채워짐).

> **일부 대체됨 (2026-07-16, ADR-0005)**: `Session`의 `generated_ko`/`generated_en` 단일 필드는 `pages` JSONB(페이지 분할 구조)로 대체되고 `lang` 필드가 추가됐다. API 경계·엔드포인트 구성 등 나머지 결정은 유효하다.

확정 API 5개: `GET /api/stories`(서가), `GET /api/stories/{id}`(상세), `POST /api/stories/{id}/generate`(구술→LLM→뒷이야기 한/영, Session 저장), `GET /api/sessions/{id}`(결과·영수증), `GET /api/sessions/{id}/pdf`(A5 완전본 PDF). 런타임 생성 지점은 `generate` 하나로 수렴 — 나머지는 정적 읽기.

PDF는 WeasyPrint(HTML+CSS→PDF), A5 한 페이지씩, 표지+원작 앞부분+아이가 쓴 뒷부분 완전본. STT는 브라우저 Web Speech API + 수정 가능 텍스트박스(진행자 보정). 화면2 소개영상은 이야기당 사전제작 영상 재생(`<video>` + 경로).

> **일부 대체됨 (2026-07-17, ADR-0006)**: PDF 엔진은 WeasyPrint가 Windows GTK 의존 문제로 기각되고 Playwright(Chromium)로 교체됐다. A5·완전본 구성 등 나머지는 유효하다.

## 기각 대안

- 서버 STT 엔드포인트: 오디오 업로드·API키·네트워크 왕복으로 실패 지점 추가 — 브라우저 처리로 불필요.
- 실시간 아바타 영상 생성: 4주 스코프 초과, 시연 중 생성 실패 치명 — 사전제작으로 대체.
- reportlab PDF: 좌표를 코드로 지정해야 해 디자인 담당이 못 건드림 — WeasyPrint로 협업 병목 제거.
- 로그인·아카이브·사진저장: 워크숍 단발 세션이라 상태 영속 불필요.

## Consequences

- 긍정: 시연 중 죽을 수 있는 지점이 `generate` LLM 호출 하나로 좁혀짐. 정적 데이터 읽기는 실패 거의 없음.
- 부정: 이야기 등록이 코드/시드 수준이라 운영 중 이야기 추가는 재배포 필요(1~2편이라 무관).
- 리스크: `generate` 실패 시 전체 골든패스 중단 — 오프라인 폴백 샘플 PDF로 완화(W5 준비).
