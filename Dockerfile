FROM python:3.13.2-slim AS builder

# Установка зависимостей для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Установка uv
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# Копирование файлов зависимостей
COPY pyproject.toml uv.lock ./

# Установка зависимостей
RUN uv sync --frozen --no-install-project --no-dev \
    && rm -rf /root/.cache/uv/*

# --- Runtime stage ---
FROM python:3.13.2-slim AS runtime

# Установка runtime зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 ca-certificates \
    libmagic1 \
    ffmpeg \
    postgresql-client \
    redis-tools \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Копирование uv и виртуального окружения
COPY --from=builder /root/.local/bin/uv /usr/local/bin/uv
COPY --from=builder /app/.venv /app/.venv

WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Копирование всего проекта
COPY . .

# Исправление окончаний строк и установка прав на выполнение
RUN sed -i 's/\r$//' /app/entrypoint.sh && \
    sed -i 's/\r$//' /app/worker.sh && \
    chmod +x /app/entrypoint.sh && \
    chmod +x /app/worker.sh

# По умолчанию запускаем API
ENTRYPOINT ["/app/entrypoint.sh"]
