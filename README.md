# 🐸 우리 전래동화 AI 도서관 (2026-LIBRARY)

> **100년 전 딱지본 옛이야기를 아동의 상상력으로 이어 쓰는 인터랙티브 그림책 생성 플랫폼**  
> 2026 도서관 데이터 활용 공모전 — 융합콘텐츠 제작 부문 출품작

---

## 📌 프로젝트 개요
도서관에 잠들어 있는 100년 전 딱지본 전래동화 데이터를 발굴하고, 아동의 간헐적 구술(Speech) 데이터를 LLM을 통해 유기적인 동화 서사로 복원하는 도서관 워크숍용 웹 서비스입니다. 최종적으로 그림 빈칸이 포함된 A5 규격의 제본용 PDF와 도서관 빅데이터 기반의 '상상 영수증(도서 추천 목록)'을 출력하여 독서 선순환을 유도합니다.

## 👥 팀원 및 역할 (Roles)

| 역할 | 담당 | 핵심 기여 내용 |
|------|------|------|
| **AI & Data**<br>(Leader) | **본인 (hs1481)** | • `Groq Llama-3.1` 및 `Whisper-large-v3` 기반 오디오-텍스트-JSON 파이프라인 설계<br>• 아동 구술 단절 극복을 위한 **'증분형 텍스트 누적 인터페이스'** 가이드 제안<br>• 도서관 정보나루 빅데이터 API 연동 및 **3계층 서비스 폴백(Fallback) 데이터 엔지니어링**<br>• 잊힌 옛이야기(딱지본) 발굴 및 서비스 원천 데이터셋(`data/`) 구축 |
| **Development** | 팀원 (개발) | • FastAPI 기반 백엔드 아키텍처 및 데이터베이스(PostgreSQL) 구축<br>• Jinja2 + WeasyPrint/Playwright 기반 A5 그림책 PDF 렌더링 파이프라인 구현<br>• Vanilla HTML/CSS/JS 프론트엔드 라우팅 및 Web Speech API 연동 |
| **Design** | 팀원 (디자인) | • 고려청자 색감 팔레트 기반의 웹 UI/UX 목업 디자인<br>• 제본용 A5 그림책 레이아웃 및 상상 영수증 출력 템플릿 가이드라인 제작 |

## 📂 프로젝트 문서 목록

| 문서 | 내용 |
|------|------|
| [docs/PLAN.md](docs/PLAN.md) | 컨셉·주차별 일정·역할·핸드오프 표 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 시스템 아키텍처 설계 (FR/NFR, 3계층 폴백, 데이터 스키마) |
| [data/kongjwi_seed.txt](data/kongjwi_seed.txt) | **[AI 담당 기여]** 콩쥐팥쥐 원문 요약 및 네트워크 장애 대응용 고정 폴백 데이터셋 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 협업을 위한 브랜치전략·PR·커밋 규칙 |
| [RULES.md](RULES.md) | 공모전 규칙·심사기준 요약 |

## 🛠️ 기술 스택 (Technical Stacks)

- **AI Engine**: Groq API (`Llama-3.1-8b-instant`, `Whisper-large-v3`)
- **Data API**: 도서관 정보나루(오픈 API), 국립중앙도서관 국가서지 표준데이터(KORMARC)
- **Backend & Database**: Python 3.11, FastAPI, PostgreSQL, SQLAlchemy
- **Environment & Infrastructure**: Git/GitHub, Render

## 🚀 진행 상황 (Milestones)

- [O] **W1**: 아이디어 확정, 저장소 개설, 도서관 데이터 오픈 API 인증키 권한 신청
- [O] **W1**: MVP 타겟 도서(콩쥐팥쥐) 선정 및 시스템 장애 방어용 폴백(Fallback) 도서 데이터 빌드업 완료
- [ ] **W2**: `backend/app/services/llm.py` 내 Groq JSON 강제 출력 프롬프트 가드레일 구현 및 백엔드 연동 테스트 (예정)

