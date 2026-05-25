#!/usr/bin/env bash
set -euo pipefail

echo "=== PM Assistant API Server ==="

# Ждем готовности PostgreSQL
echo "Ожидание PostgreSQL..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
  if pg_isready -h ${POSTGRES_HOST:-postgres} -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER:-pm_user} > /dev/null 2>&1; then
    echo "PostgreSQL готов!"
    break
  fi
  retry_count=$((retry_count + 1))
  echo "Попытка $retry_count из $max_retries..."
  sleep 1
done

if [ $retry_count -eq $max_retries ]; then
  echo "ОШИБКА: PostgreSQL не готов после $max_retries попыток"
  exit 1
fi

# Применение миграций
echo "Применение миграций БД..."
/app/.venv/bin/alembic upgrade head

# Запуск API сервера
echo "Запуск API сервера на порту ${PORT:-8000}..."
exec /app/.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --reload