# Python 3.13 with uv preinstalled
FROM ghcr.io/astral-sh/uv:python3.13-bookworm AS base
WORKDIR /app

# Project metadata first for layer caching
COPY pyproject.toml ./
# COPY uv.lock ./   # uncomment if you generate a lock for reproducible builds

# Install deps into .venv
RUN uv sync --no-dev

# App code
COPY app ./app

# Non-root
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

