# ADR-0006: PDF 엔진 — WeasyPrint에서 Playwright(Chromium)로 교체

날짜: 2026-07-17 / 상태: accepted
관련: ADR-0001의 WeasyPrint 결정을 대체

## Context

W1 PoC에서 WeasyPrint가 Windows에서 GTK 런타임(`libgobject-2.0-0`) 부재로 import조차 실패했다. GTK를 설치하면 되지만 그 부담이 세 곳에 전파된다: 개발 PC(수동 설치), 워크숍 노트북(현장 세팅 리스크), Render 배포(네이티브 환경에 pango가 없어 Docker 전환 필요). 한편 디자이너 목업은 브라우저 CSS(aspect-ratio, CSS 변수, flex)로 작성되어 있어 WeasyPrint의 CSS 지원 범위와 어긋날 가능성도 있었다.

## Decision

**Playwright(Chromium headless) print-to-PDF**로 교체. `pip install playwright && playwright install chromium`만으로 전 환경에서 동일하게 동작하며 시스템 DLL 의존이 없다. PoC 검증 완료: A5(148.2×210mm) 5페이지(표지·본문 3·판권기), 청자색 팔레트·한글 폰트·이모지·점선 그림빈칸 레이아웃 전부 정상 렌더링.

부가 이점: 화면 목업과 PDF가 **같은 Chromium 엔진**으로 렌더링되어, 디자이너가 브라우저에서 미리보기한 그대로 인쇄물이 나온다 — "화면=인쇄물 톤 일치"(완성도 40점 요건)가 구조적으로 보장된다.

## 기각 대안

- **WeasyPrint + GTK 런타임 설치**: 개발 PC·워크숍 노트북·Render(Docker화) 세 곳에 설치 부담 전파. 워크숍 당일 새 노트북에서 세팅이 안 되는 시나리오가 치명적.
- **reportlab**: ADR-0001에서 이미 기각 (디자이너가 좌표 코드를 못 다룸).

## Consequences

- 긍정: pip만으로 환경 구성 완결. 디자이너 HTML/CSS를 무수정으로 templates에 흡수 가능. 화면·인쇄물 렌더링 일치.
- 부정: Chromium 바이너리 ~114MB — 배포 슬러그 커짐. Render 무료 티어(512MB RAM)에서 렌더링 시 메모리 여유 확인 필요(단, PDF는 5~7페이지 소형이라 문제 가능성 낮음. 배포는 어차피 제출·녹화용이며 워크숍은 로컬).
- 리스크: Render 빌드에서 `playwright install chromium` 단계를 build command에 넣어야 함 — 누락 시 배포본만 PDF 실패. W4 배포 점검 항목에 포함.
