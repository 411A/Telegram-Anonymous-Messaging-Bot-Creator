# syntax=docker/dockerfile:1
# Lightweight, cache-sharing multi-stage build for HiddenEgo bot.
#
# Centralized-dependency design (mutual with other Python projects on host):
#   - All Python services standardize on ARG PYTHON_BASE (default python:3.12-slim),
#     so Docker shares the base layers on disk instead of storing one per project.
#   - pip downloads use a BuildKit cache mount (--mount=type=cache), which is
#     daemon-global: every project that uses the same pattern reuses downloads.
#   - No per-project pip cache directories are baked into the final image.

ARG PYTHON_BASE=python:3.12-slim

# ---------------------------------------------------------------- builder ---
FROM ${PYTHON_BASE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0

WORKDIR /build

# Build tools only live in this stage (never shipped to runtime).
# cache mounts for apt + pip are shared daemon-wide with other Python projects.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --prefix=/install --no-warn-script-location -r requirements.txt

# ---------------------------------------------------------------- runtime ---
FROM ${PYTHON_BASE} AS runtime

# OCI + project labels: used by run.sh prune to scope cleanup to THIS project.
LABEL org.opencontainers.image.title="hidego-tgbot" \
      org.opencontainers.image.description="HiddenEgo Telegram Anonymous Messaging Bot" \
      org.hidego.project="hidego-tgbot"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DOCKER_ENV=1

WORKDIR /app

# Runtime deps only: ca-certificates for TLS (slim lacks full set on some hosts).
# No curl: healthchecks use python stdlib (urllib), saving ~15MB + CVE surface.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Installed third-party packages from the builder (no build tools, no caches).
COPY --from=builder /install /usr/local

# Application code (heavy, never-imported assets like src/assets/*.mp4 are
# excluded via the root .dockerignore, saving ~33MB).
COPY src/ ./src/
COPY main_bot_onetime_settings.py .
COPY pyproject.toml .
COPY .dockerignore .

# Pre-compile bytecode at build time. Runtime sets PYTHONDONTWRITEBYTECODE=1,
# so without this every container start recompiles the whole app from source.
RUN python -m compileall -q src main_bot_onetime_settings.py

# Startup script
COPY docker/docker_entrypoint.sh .
RUN chmod +x docker_entrypoint.sh

# Runs as ${USER_UID}:${USER_GID} via docker-compose (bind-mount friendly).
# No USER directive here so root-owned image files stay readable for any UID.

# Documentation only; runtime mapping remains controlled by .env/compose.
EXPOSE 13360

# Python-based healthcheck: no curl binary needed in the image.
# 300s interval: each probe starts a fresh Python interpreter, so 60s polling
# burned CPU quota for no practical benefit on a stable, 24/7 bot.
HEALTHCHECK --interval=300s --timeout=10s --retries=3 --start-period=120s \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('FASTAPI_PORT','13360'),timeout=8)" || exit 1

ENTRYPOINT ["./docker_entrypoint.sh"]
