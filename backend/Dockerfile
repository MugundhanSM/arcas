# ARCAS backend image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# git for semgrep, libpq for psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# bump this on bigger machines, e.g. UVICORN_WORKERS=$(nproc)
ENV UVICORN_WORKERS=2

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}
