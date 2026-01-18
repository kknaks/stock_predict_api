FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Poetry 설치
RUN pip install poetry

# Poetry 가상환경 비활성화 (컨테이너 내에서는 불필요)
RUN poetry config virtualenvs.create false

# 의존성 파일 복사
COPY pyproject.toml poetry.lock ./

# 의존성 설치 (dev 제외)
RUN poetry install --no-root --only main

# 애플리케이션 코드 복사
COPY app ./app

# 포트 노출
EXPOSE 8003

# 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
