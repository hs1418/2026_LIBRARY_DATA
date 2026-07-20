# 우리 전래동화 AI 도서관

100년 전 딱지본 옛이야기의 뒷이야기를 아이가 말로 지어내면, AI가 아이 말투를 살린 동화체로 정리해 그림 빈칸이 있는 A5 그림책 PDF로 제본하는 도서관 워크숍 도구.

2026 도서관 데이터 활용 공모전 — 융합콘텐츠 제작 부문 출품작.

## 팀

| 역할 | 담당 |
|------|------|
| 개발 | 백엔드·PDF 렌더러·웹 (도연우) |
| AI | 도서관 데이터 API·원문 OCR·프롬프트 설계 |
| 디자인 | 그림책·영수증 템플릿, 화면 UI |

## 문서 (팀원은 여기부터)

| 문서 | 내용 |
|------|------|
| [docs/PLAN.md](docs/PLAN.md) | 컨셉·주차별 일정·역할·핸드오프 표 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 시스템 설계 전체 (FR/NFR·API·다이어그램) |
| [docs/adr/](docs/adr/README.md) | 설계 결정 기록 (왜 이렇게 정했는가) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 브랜치·PR·커밋 규칙 |
| [CLAUDE.md](CLAUDE.md) | 공모전 규칙·심사기준 요약 |

## 실행

준비 중 — W2에 백엔드 골격이 올라오면 갱신.

```
backend/poc_pdf.py  # A5 그림책 PDF 렌더링 검증 (Playwright/Chromium)
```

