# syntax=docker/dockerfile:1

# Etapa 1: instalar dependencias con uv.
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Solo los archivos de dependencias: esta capa se reutiliza mientras uv.lock no cambie.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Etapa 2: imagen de ejecución, sin uv.
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 1000 agente

WORKDIR /app

COPY --from=builder --chown=agente:agente /app/.venv ./.venv
COPY --chown=agente:agente app ./app
COPY --chown=agente:agente controllers ./controllers
COPY --chown=agente:agente services ./services
COPY --chown=agente:agente agents ./agents
COPY --chown=agente:agente vectorstore ./vectorstore
COPY --chown=agente:agente data ./data

USER agente

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
