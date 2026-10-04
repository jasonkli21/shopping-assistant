.PHONY: db-up db-down install api web migrate test lint typecheck build validate format

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
	cd apps/api && uv run pytest
	cd apps/web && pnpm test

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

validate: lint test typecheck build
