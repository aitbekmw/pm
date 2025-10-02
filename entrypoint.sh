#!/usr/bin/env bash
set -euo pipefail


if [ -z "${DATABASE_URL:-}" ]; then
    exit 1
fi

ALEMBIC_CMD="uv run alembic"
PORT=${PORT:-8000}

echo "upgrade head"
${ALEMBIC_CMD} upgrade head

uv run -m src.main &
MAIN_PID=$!

uv run uvicorn src.main:app --host 0.0.0.0 --port "${PORT}" &
UVICORN_PID=$!

trap 'kill -TERM ${MAIN_PID} ${UVICORN_PID} 2>/dev/null || true' TERM INT
wait ${MAIN_PID} ${UVICORN_PID}
