FROM python:3.13.2-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev \
    && rm -rf /root/.cache/uv/*

# --- Runtime stage ---
FROM python:3.13.2-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 ca-certificates \
    libmagic1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local/bin/uv /usr/local/bin/uv
COPY --from=builder /app/.venv /app/.venv

WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY . .

# Fix line endings and make executable
RUN sed -i 's/\r$//' /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]