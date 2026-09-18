FROM python:3.14.7-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY alembic.ini start.sh ./
COPY migrations ./migrations

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA} PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["sh", "start.sh"]
