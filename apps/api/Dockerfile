FROM ghcr.io/astral-sh/uv:0.11.13 AS uv

FROM python:3.12-slim-bookworm AS builder
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/api/src \
    SHOPPING_REPOSITORY_ROOT=/app \
    ENVIRONMENT=production

WORKDIR /app/apps/api
COPY --from=builder /opt/venv /opt/venv
COPY apps/api/src ./src
COPY apps/api/migrations ./migrations
COPY apps/api/alembic.ini ./alembic.ini
USER 10001:10001
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn shopping.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
