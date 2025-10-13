#!/usr/bin/env bash

set -euo pipefail

echo "=== PM Assistant ARQ Worker ==="

# Ждем готовности Redis
echo "Ожидание Redis..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if redis-cli -h ${REDIS_HOST:-redis} -p ${REDIS_PORT:-6379} ping > /dev/null 2>&1; then
        echo "Redis готов!"
        break
    fi
    retry_count=$((retry_count + 1))
    echo "Попытка $retry_count из $max_retries..."
    sleep 1
done

if [ $retry_count -eq $max_retries ]; then
    echo "ВНИМАНИЕ: Redis не готов, но продолжаем запуск worker..."
fi

# Запуск ARQ worker
echo "Запуск ARQ Worker для обработки встреч..."
exec arq src.core.tasks.WorkerSettings
