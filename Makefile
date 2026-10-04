.PHONY: db-up db-down install api web migrate test test-db lint typecheck build validate format api-types api-types-check

install:
	cd apps/api && uv sync --locked --extra dev
	cd apps/web && pnpm install --frozen-lockfile

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

api:
	cd apps/api && uv run uvicorn shopping.main:app --reload --port 8000

web:
	cd apps/web && pnpm dev

test:
	cd apps/api && uv run pytest -m 'not db and not live'
	cd apps/web && pnpm test
	@echo "PostgreSQL integration tests are separate; run make test-db TEST_DATABASE_URL=..."

test-db:
	cd apps/api && TEST_DATABASE_URL="$(TEST_DATABASE_URL)" uv run pytest -m db

api-types:
	cd apps/api && uv run python ../../scripts/generate_api_types.py

api-types-check:
	cd apps/api && uv run python ../../scripts/generate_api_types.py --check

lint:
	cd apps/api && uv run ruff check src tests migrations
	cd apps/api && uv run ruff format --check src tests migrations
	cd apps/web && pnpm lint

format:
	cd apps/api && uv run ruff format src tests migrations

migrate:
	cd apps/api && uv run alembic upgrade head

typecheck:
	cd apps/web && pnpm typecheck

build:
	cd apps/web && pnpm build

validate: lint test api-types-check typecheck build
