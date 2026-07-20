# 협업 규칙 — 브랜치·PR·커밋

> 3인 팀 · 내부마감 2026-08-02. 규칙은 최소한으로 두되, 이것만은 지킨다.

## 브랜치

- `main` — 보호 브랜치. **직접 푸시 금지, PR로만 병합.** 항상 시연 가능한 상태를 유지한다.
- 작업 브랜치 이름: `<타입>/<짧은-설명>` (kebab-case)
  - `feat/pdf-renderer`, `fix/stt-textbox`, `docs/architecture`, `design/book-template`, `chore/ci-setup`
- 브랜치는 작게 — 하나의 브랜치는 하나의 목적. 3일 넘게 살아있는 브랜치는 쪼갠다.

## PR

- 템플릿(.github/PULL_REQUEST_TEMPLATE.md)의 4칸을 채운다: 목적 / 변경 내용 / 확인 방법 / 관련 문서(ADR).
- **승인 없이 셀프 머지 허용** — 코드 리뷰 가능 인원이 사실상 1인이라 승인 필수는 병목이 된다. 대신 PR을 남기는 것 자체가 목적(변경 이력·이유 기록).
- 병합은 **Squash merge** — main 히스토리를 커밋 컨벤션 단위로 깔끔하게 유지.
- 디자인의 HTML/CSS 템플릿도 PR로 — `design/` 브랜치 사용, 개발자가 확인 후 병합.

## 커밋 컨벤션

`<타입>: <내용>` — 타입: `feat` `fix` `refactor` `docs` `chore` `test` `design`

```
feat: A5 그림책 PDF 렌더러 추가 (Playwright)
docs: ADR-0006 PDF 엔진 교체 기록
design: 표지·판권기 템플릿 초안
```

## 금지 사항

- `.env`·API 키 커밋 금지 — `.env.example`만 커밋. 키가 커밋되면 즉시 폐기·재발급.
- `main` 직접 푸시 금지 (보호 규칙으로 강제됨).
- 스코프 밖 기능 추가 금지 — PLAN.md의 MVP 범위·YAGNI 목록이 기준. 추가하고 싶으면 PR 전에 논의.

## 문서 위치

| 무엇 | 어디 |
|------|------|
| 컨셉·일정·역할·핸드오프 | [PLAN.md](PLAN.md) |
| 시스템 설계 전체 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 공모전 규칙·심사기준 | [RULES.md](RULES.md) |
