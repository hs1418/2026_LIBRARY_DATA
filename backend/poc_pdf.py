"""WeasyPrint 대체 검증 PoC — Playwright(Chromium)로 A5 그림책 PDF 렌더링.

검증 항목:
1. A5(148x210mm) 페이지가 정확한 크기로 나오는가
2. 상단 그림 빈칸(점선) + 하단 글 레이아웃이 유지되는가
3. 디자이너 목업의 CSS 변수·한글 폰트가 렌더링되는가
4. 표지 + 본문 3页 + 판권기 = 5페이지 완전본 구조
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

# 디자이너 목업의 팔레트를 그대로 공유 (화면=인쇄물 톤 일치)
HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<style>
  :root {
    --bg-paper: #F6F5F2;
    --primary-celadon: #4A7C68;
    --celadon-light: #E4ECE8;
    --text-main: #2C2A29;
    --text-sub: #7A827F;
  }
  @page { size: 148mm 210mm; margin: 0; }
  * { margin: 0; box-sizing: border-box; }
  body { font-family: 'Malgun Gothic', sans-serif; }
  .page {
    width: 148mm; height: 210mm;
    page-break-after: always;
    background: var(--bg-paper);
    display: flex; flex-direction: column;
    padding: 12mm;
  }
  /* 표지 */
  .cover { justify-content: center; align-items: center; text-align: center;
           background: var(--celadon-light); }
  .cover .emoji { font-size: 40pt; margin-bottom: 8mm; }
  .cover h1 { font-size: 24pt; color: var(--primary-celadon); margin-bottom: 4mm; }
  .cover .author { font-size: 12pt; color: var(--text-sub); }
  /* 본문: 상단 그림 빈칸 + 하단 글 */
  .draw-box {
    flex: 1;
    border: 1.2mm dashed rgba(74, 124, 104, 0.4);
    border-radius: 4mm;
    display: flex; justify-content: center; align-items: center;
    color: var(--text-sub); font-size: 9pt;
  }
  .text-box { padding-top: 8mm; }
  .text-ko { font-size: 13pt; line-height: 1.7; color: var(--text-main); }
  .text-en { font-size: 9pt; line-height: 1.5; color: var(--primary-celadon); margin-top: 3mm; }
  .page-no { text-align: center; color: var(--text-sub); font-size: 8pt; margin-top: 4mm; }
  /* 판권기 */
  .colophon { justify-content: flex-end; }
  .colophon .box { border-top: 0.5mm solid var(--primary-celadon); padding-top: 5mm;
                   font-size: 8.5pt; line-height: 1.8; color: var(--text-sub); }
</style>
</head>
<body>
  <div class="page cover">
    <div class="emoji">🐸</div>
    <h1>콩쥐팥쥐</h1>
    <div class="author">글·그림 김토스 | 원작: 100년 전 딱지본</div>
  </div>
  <div class="page">
    <div class="draw-box">🖍️ 그림 그리는 곳</div>
    <div class="text-box">
      <div class="text-ko">두꺼비가 커다란 몸으로 깨진 독을 막아 주었어요.</div>
      <div class="text-en">The toad blocked the broken pot with its big body.</div>
    </div>
    <div class="page-no">1</div>
  </div>
  <div class="page">
    <div class="draw-box">🖍️ 그림 그리는 곳</div>
    <div class="text-box">
      <div class="text-ko">콩쥐는 물을 가득 채우고 고운 옷을 입었어요.</div>
      <div class="text-en">Kongjwi filled the pot and put on pretty clothes.</div>
    </div>
    <div class="page-no">2</div>
  </div>
  <div class="page">
    <div class="draw-box">🖍️ 그림 그리는 곳</div>
    <div class="text-box">
      <div class="text-ko">그래서 콩쥐는 잔치에 무사히 갈 수 있었답니다.</div>
      <div class="text-en">So Kongjwi could safely go to the party.</div>
    </div>
    <div class="page-no">3</div>
  </div>
  <div class="page colophon">
    <div class="box">
      원작: 『콩쥐팥쥐전』 1926년 ○○서관 발행 (국립중앙도서관 소장)<br>
      이 책은 콩쥐팥쥐 이야기의 스물세 번째 판본입니다.<br>
      2026 도서관 데이터 활용 공모전 · 우리 전래동화 AI 도서관
    </div>
  </div>
</body>
</html>"""


async def main() -> None:
    out = Path(__file__).parent / "poc_output.pdf"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(HTML)
        await page.pdf(
            path=str(out),
            width="148mm",
            height="210mm",
            print_background=True,  # 배경색·팔레트 유지에 필수
        )
        await browser.close()
    print(f"OK: {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
