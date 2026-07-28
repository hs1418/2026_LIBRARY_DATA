이 폴더에 북뷰어(화면3) 페이지 삽화를 넣습니다.

- 경로 규칙: `story/{slug}/p{n}.jpg` — slug 는 seed.py 의 `STORY_SLUGS`, n 은 시드 파일의
  `INTRO_PAGE_n` 번호입니다 (예: 콩쥐팥쥐전 3쪽 → `story/kongjwi/p3.jpg`)
- 파일이 없으면 그림 자리가 청자색 플레이스홀더로 채워집니다. 파일을 넣고 재시딩하면
  (`python -m app.seed`, dev.db 삭제 후) 자동으로 표시됩니다 — 코드 수정 불필요
- 권장 비율은 4:3 가로(북뷰어 그림 영역이 가로로 넓습니다)
- 담당: 디자인팀
