# Render 배포용 (ADR-0003, ADR-0006)
#
# 네이티브 Python 런타임에서는 `playwright install --with-deps` 가 apt-get 을 위해
# root 로 전환하다 실패하고(su: Authentication failure), --with-deps 를 빼면
# 브라우저 바이너리는 깔리지만 시스템 라이브러리가 없어 PDF 생성만 500 이 난다.
# Docker 안에서는 root 라 라이브러리까지 함께 설치할 수 있다.
#
# 레이아웃 주의: app/main.py 가 프론트를 ../../frontend 로 찾으므로
# backend/ 와 frontend/ 를 같은 부모(/app) 아래 그대로 둔다.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

# 브라우저 + 시스템 라이브러리. 의존성이 잘 안 바뀌므로 소스 복사보다 앞에 두어 캐시를 살린다.
RUN python -m playwright install --with-deps chromium

COPY backend/ backend/
COPY frontend/ frontend/
# 시드 데이터(전래동화 10선)의 진실 소스는 AI/data/ 다 — app/seed.py 가 런타임에 읽는다.
# 이 COPY 가 빠지면 배포본이 시딩에 실패해 서가가 비거나 옛 데이터로 돌아간다(실제 발생).
COPY AI/data/ AI/data/

WORKDIR /app/backend

# 배포본은 디스크가 재기동마다 초기화되므로 매번 테이블 생성 + 시드(멱등).
CMD ["sh", "-c", "python -m app.bootstrap && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
