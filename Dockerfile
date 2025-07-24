FROM python:3.12-slim-bullseye AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.8.3

RUN poetry config virtualenvs.create false

WORKDIR /app

COPY pyproject.toml poetry.lock ./

# ⛔ Don’t regenerate the lock — just install exactly what’s in it
RUN poetry install --no-root --only main --no-ansi --no-interaction

RUN apt-get purge -y gcc && rm -rf /var/lib/apt/lists/*

COPY ./src ./src
COPY ./scripts /scripts
