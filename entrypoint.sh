#!/usr/bin/env bash
set -euo pipefail

ALEMBIC_CMD="uv run alembic"
API_PORT=8000

echo "Выполняю миграции: upgrade head"
${ALEMBIC_CMD} upgrade head

echo "Запускаю сервисы..."
uv run -m src.main &
MAIN_PID=$!

uv run uvicorn src.server:app --host 0.0.0.0 --port ${API_PORT} &
UVICORN_PID=$!

trap 'kill -TERM ${MAIN_PID} ${UVICORN_PID} 2>/dev/null || true' TERM INT
wait ${MAIN_PID} ${UVICORN_PID}