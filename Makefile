.PHONY: help build up down logs restart clean migrate migrate-create dev-up dev-down test lint format

help:
	@echo "PM Assistant - Команды управления"
	@echo ""
	@echo "Разработка:"
	@echo "  dev-up          - Запустить PostgreSQL и Redis для локальной разработки"
	@echo "  dev-down        - Остановить сервисы разработки"
	@echo "  migrate         - Применить миграции БД"
	@echo "  migrate-create  - Создать новую миграцию"
	@echo ""
	@echo "Production (Docker):"
	@echo "  build           - Собрать Docker образ"
	@echo "  up              - Запустить все сервисы"
	@echo "  down            - Остановить все сервисы"
	@echo "  logs            - Показать логи"
	@echo "  restart         - Перезапустить сервисы"
	@echo "  clean           - Остановить и удалить все (включая volumes)"
	@echo ""
	@echo "Качество кода:"
	@echo "  lint            - Запустить линтеры"
	@echo "  format          - Форматировать код"
	@echo "  test            - Запустить тесты"

# Разработка
dev-up:
	docker compose -f docker-compose.dev.yml up -d
	@echo "PostgreSQL и Redis запущены для разработки"
	@echo "Для запуска API: uv run uvicorn src.main:app --reload"
	@echo "Для запуска Worker: uv run arq src.core.tasks.WorkerSettings"

dev-down:
	docker compose -f docker-compose.dev.yml down

migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Название миграции: " name; \
	uv run alembic revision --autogenerate -m "$$name"

# Production
build:
	docker compose build

up:
	docker compose up -d
	@echo "Ожидание запуска сервисов..."
	@sleep 5
	docker compose exec api alembic upgrade head
	@echo ""
	@echo "PM Assistant запущен!"
	@echo "API: http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart

clean:
	docker compose down -v
	@echo "Все контейнеры и данные удалены"

# Качество кода
lint:
	uv run flake8 src tests
	uv run black --check src tests

format:
	uv run black src tests
	uv run isort src tests

test:
	uv run pytest tests/ -v

