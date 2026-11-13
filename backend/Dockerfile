# =============================================================================
# Builder: install dependencies into /app/.venv with uv
# =============================================================================
FROM python:3.14-alpine AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Compiler toolchain for any package without a prebuilt musl wheel. Builder stage only.
RUN apk add --no-cache build-base

WORKDIR /app

# 1) Dependencies only: this layer is reused until pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Our own code, installed into the same venv as a normal (non-editable) package.
COPY app/ ./app/
RUN uv sync --frozen --no-dev --no-editable

# =============================================================================
# Runtime: only the finished virtualenv + migrations, run as a non-root user
# =============================================================================
FROM python:3.14-alpine

ARG UID=10001
ARG GID=10001

RUN apk add --no-cache bash ca-certificates font-dejavu

RUN addgroup -g ${GID} appuser && \
    adduser -u ${UID} -G appuser -D -s /sbin/nologin appuser

# The venv arrives fully built, so pip is never needed at runtime.
RUN python -m pip uninstall -y pip && \
    rm -rf /usr/local/lib/python3.14/site-packages/pip*

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser alembic/ /app/alembic
COPY --chown=appuser:appuser alembic.ini /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

USER appuser

EXPOSE 8080

# Migrations run from the app's startup hook when RUN_ALEMBIC_ON_STARTUP=true.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]