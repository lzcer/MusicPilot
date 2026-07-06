ARG UV_IMAGE=ghcr.io/astral-sh/uv:latest
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM ${UV_IMAGE} AS uv

FROM python:3.12-slim AS runtime
COPY --from=uv /uv /uvx /usr/local/bin/
ARG UV_DEFAULT_INDEX=https://pypi.org/simple
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONMALLOC=malloc \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    MP_DATABASE_URL=sqlite+aiosqlite:////data/musicpilot.db \
    MP_MUSIC_LIBRARY_PATH=/music \
    MP_DOWNLOAD_STAGING_PATH=/downloads \
    MP_STATIC_DIR=/app/frontend/dist \
    MP_INDEXER_PARSER_CONFIG=/config/sites.parser.yaml \
    MP_RUNTIME_CONFIG=/config/runtime.json
WORKDIR /app
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=120 \
    UV_HTTP_RETRIES=5 \
    uv pip install \
      --system \
      --verbose \
      --default-index "${UV_DEFAULT_INDEX}" \
      "setuptools>=68" \
      wheel \
    && uv pip install \
      --system \
      --verbose \
      --default-index "${UV_DEFAULT_INDEX}" \
      -r pyproject.toml
COPY README.md LICENSE ./
COPY musicpilot ./musicpilot
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=120 \
    UV_HTTP_RETRIES=5 \
    uv pip install \
      --system \
      --verbose \
      --default-index "${UV_DEFAULT_INDEX}" \
      --no-deps \
      --no-build-isolation \
      .
COPY config ./config
RUN mkdir -p /data /music /downloads /config
COPY --from=frontend /app/frontend/dist /app/frontend/dist
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/health', timeout=5).read()" || exit 1
CMD ["uvicorn", "musicpilot.infra.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
