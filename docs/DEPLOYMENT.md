# PM Assistant - Руководство по развертыванию

## 📋 Предварительные требования

### Обязательно

1. **Docker** и **Docker Compose** (версия 2.0+)
2. **MinIO S3** сервер (внешний) - для хранения аудио файлов
3. **OpenAI API ключ** - для транскрибации и суммаризации
4. **Active Directory** сервер (опционально, для production)

### Опционально для разработки

- Python 3.11+ и uv (для локальной разработки)
- PostgreSQL 17 (если не используете Docker)
- Redis 7 (если не используете Docker)

## 🚀 Быстрое развертывание (Production)

### 1. Клонирование и настройка

```bash
# Клонировать репозиторий
git clone <repository-url>
cd pm-assistant

# Создать .env файл
cp env.example .env
```

### 2. Настройка переменных окружения

Отредактируйте `.env` файл:

```bash
# ОБЯЗАТЕЛЬНО настроить:

# MinIO S3 (ваш внешний сервер)
S3_ENDPOINT_URL=http://your-minio-server:9000
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_BUCKET_NAME=pm-assistant

# OpenAI
OPENAI_API_KEY=sk-your-openai-api-key-here

# Active Directory (для production)
AD_SERVER=ldap://your-ad-server.com
AD_DOMAIN=YOUR_DOMAIN
AD_BASE_DN=DC=your,DC=domain,DC=com

# База данных (можно оставить по умолчанию)
DATABASE_URL=postgresql+asyncpg://pm_user:pm_password@postgres:5432/pm_assistant
POSTGRES_USER=pm_user
POSTGRES_PASSWORD=pm_password
POSTGRES_DB=pm_assistant
```

### 3. Запуск

```bash
# Использовать Makefile (рекомендуется)
make up

# ИЛИ вручную
docker compose up -d
sleep 5
docker compose exec api alembic upgrade head
```

### 4. Проверка

```bash
# Проверить статус
docker compose ps

# Проверить логи
docker compose logs -f

# Открыть API документацию
open http://localhost:8000/docs
```

## 🛠️ Локальная разработка

### 1. Установка зависимостей

```bash
# Установить uv (если еще не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Установить зависимости проекта
uv sync
```

### 2. Запуск сервисов для разработки

```bash
# Запустить только PostgreSQL и Redis
make dev-up

# ИЛИ вручную
docker compose -f docker-compose.dev.yml up -d
```

### 3. Создать .env для локальной разработки

```bash
cp env.example .env

# Отредактировать для локального окружения:
DATABASE_URL=postgresql+asyncpg://pm_user:pm_password@localhost:5432/pm_assistant
REDIS_URL=redis://localhost:6379
POSTGRES_HOST=localhost
REDIS_HOST=localhost
```

### 4. Применить миграции

```bash
make migrate

# ИЛИ
uv run alembic upgrade head
```

### 5. Запустить API и Worker

```bash
# В первом терминале - API
uv run uvicorn src.main:app --reload --port 8000

# Во втором терминале - Worker
uv run arq src.core.tasks.WorkerSettings
```

## 🔄 Создание миграций

```bash
# Создать новую миграцию
make migrate-create
# Введите название миграции

# ИЛИ вручную
uv run alembic revision --autogenerate -m "описание изменений"

# Применить миграции
make migrate
```

## 🐳 Docker команды

### Сборка образа

```bash
make build

# ИЛИ
docker compose build
```

### Управление сервисами

```bash
# Запустить
make up

# Остановить
make down

# Перезапустить
make restart

# Логи
make logs

# Остановить и удалить ВСЕ (включая данные)
make clean
```

### Отдельные сервисы

```bash
# Перезапустить API
docker compose restart api

# Перезапустить Worker
docker compose restart worker

# Логи Worker
docker compose logs -f worker

# Логи API
docker compose logs -f api
```

## 🔐 Настройка MinIO S3

### 1. Создание bucket

```bash
# Войдите в MinIO консоль
# Создайте bucket с именем: pm-assistant

# ИЛИ через mc (MinIO Client)
mc mb myminio/pm-assistant
mc policy set public myminio/pm-assistant
```

### 2. Получение ключей доступа

```bash
# В MinIO консоли:
# 1. Перейдите в Access Keys
# 2. Create New Access Key
# 3. Скопируйте Access Key и Secret Key
# 4. Добавьте в .env файл
```

## 🧪 Тестирование API

### 1. Вход (тестовый пользователь)

```bash
# Если AD не настроен, создайте пользователя вручную в БД
# ИЛИ используйте существующего пользователя AD

curl -X POST "http://localhost:8000/api/users/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your-ad-username",
    "password": "your-password"
  }'

# Сохраните session_id из cookies для дальнейших запросов
```

### 2. Создание проекта

```bash
curl -X POST "http://localhost:8000/api/projects/" \
  -H "Cookie: session_id=YOUR_SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Тестовый проект",
    "description": "Описание проекта",
    "jira_data": {"project_key": "TEST"},
    "confluence_data": {"space_key": "TEST"}
  }'
```

### 3. Создание встречи

```bash
curl -X POST "http://localhost:8000/api/meetings/" \
  -H "Cookie: session_id=YOUR_SESSION_ID" \
  -F "title=Тестовая встреча" \
  -F "project_id=1" \
  -F "audio_file=@/path/to/audio.mp3"
```

### 4. Обработка встречи

```bash
# Запустить обработку
curl -X POST "http://localhost:8000/api/meetings/1/process" \
  -H "Cookie: session_id=YOUR_SESSION_ID"

# Проверить статус
curl "http://localhost:8000/api/meetings/1/processing-status" \
  -H "Cookie: session_id=YOUR_SESSION_ID"
```

## 📊 Мониторинг

### Проверка здоровья сервисов

```bash
# Health check API
curl http://localhost:8000/health

# Проверка PostgreSQL
docker compose exec postgres pg_isready

# Проверка Redis
docker compose exec redis redis-cli ping
```

### Логи

```bash
# Все логи
docker compose logs -f

# Только API
docker compose logs -f api

# Только Worker
docker compose logs -f worker

# Последние 100 строк
docker compose logs --tail=100
```

## 🔧 Решение проблем

### API не запускается

```bash
# Проверить логи
docker compose logs api

# Проверить миграции
docker compose exec api alembic current

# Применить миграции заново
docker compose exec api alembic upgrade head
```

### Worker не обрабатывает встречи

```bash
# Проверить логи Worker
docker compose logs worker

# Проверить Redis
docker compose exec redis redis-cli ping

# Перезапустить Worker
docker compose restart worker
```

### Проблемы с S3

```bash
# Проверить доступность MinIO
curl http://your-minio-server:9000/minio/health/live

# Проверить настройки в .env
cat .env | grep S3_

# Проверить логи API на наличие S3 ошибок
docker compose logs api | grep -i s3
```

### База данных не инициализируется

```bash
# Проверить PostgreSQL
docker compose exec postgres psql -U pm_user -d pm_assistant -c "\dt"

# Применить миграции вручную
docker compose exec api alembic upgrade head

# Если нужно пересоздать БД
docker compose down -v
docker compose up -d
sleep 5
docker compose exec api alembic upgrade head
```

## 🚀 Production развертывание

### 1. Настройка окружения

```bash
# Создать production .env
cp env.example .env.production

# Настроить:
DEBUG=false
APP_NAME=PM Assistant Production
DATABASE_URL=postgresql+asyncpg://secure_user:secure_password@postgres:5432/pm_assistant_prod

# Настроить безопасные пароли
POSTGRES_PASSWORD=<secure-password>
```

### 2. Запуск

```bash
docker compose --env-file .env.production up -d
```

### 3. Настройка reverse proxy (Nginx)

```nginx
server {
    listen 80;
    server_name pm-assistant.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 4. SSL/HTTPS (Let's Encrypt)

```bash
# Установить certbot
sudo apt install certbot python3-certbot-nginx

# Получить сертификат
sudo certbot --nginx -d pm-assistant.yourdomain.com
```

## 📈 Масштабирование

### Горизонтальное масштабирование Worker

```yaml
# docker-compose.yml
worker:
  # ... существующая конфигурация
  deploy:
    replicas: 3  # Запустить 3 worker'а
```

### Использование внешней PostgreSQL

```bash
# .env
DATABASE_URL=postgresql+asyncpg://user:password@external-db-server:5432/pm_assistant
```

### Использование внешней Redis

```bash
# .env
REDIS_URL=redis://external-redis-server:6379
REDIS_HOST=external-redis-server
```

## 📝 Чеклист развертывания

- [ ] MinIO S3 настроен и доступен
- [ ] Bucket создан в MinIO
- [ ] OpenAI API ключ получен и добавлен в .env
- [ ] Active Directory настроен (для production)
- [ ] .env файл создан и настроен
- [ ] Docker и Docker Compose установлены
- [ ] Выполнен `docker compose up -d`
- [ ] Применены миграции БД
- [ ] API доступен на http://localhost:8000/docs
- [ ] Worker запущен и обрабатывает задачи
- [ ] Тестовая встреча создана и обработана

## 🆘 Поддержка

При возникновении проблем:

1. Проверьте логи: `docker compose logs -f`
2. Проверьте статус сервисов: `docker compose ps`
3. Изучите документацию: `docs/README.md`
4. Проверьте API документацию: http://localhost:8000/docs

---

**Готово к развертыванию! 🚀**

