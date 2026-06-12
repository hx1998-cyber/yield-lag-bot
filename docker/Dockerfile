# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# baccarat — production image
# Multi-stage to keep the final image lean. We pin Python 3.11 (matches
# pyproject `requires-python`) and run as an unprivileged user.
# ---------------------------------------------------------------------------

FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for asyncpg / hiredis / cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only what's needed to resolve deps first (Docker layer cache)
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip wheel \
 && pip wheel --wheel-dir /wheels .

# ---------------------------------------------------------------------------

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    TZ=UTC

# Runtime libs only (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged user
RUN groupadd --system --gid 1000 baccarat \
 && useradd --system --uid 1000 --gid baccarat --create-home --shell /bin/bash baccarat

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels baccarat \
 && rm -rf /wheels

# Migrations + alembic config live alongside source
COPY --chown=baccarat:baccarat alembic.ini ./alembic.ini
COPY --chown=baccarat:baccarat migrations ./migrations
COPY --chown=baccarat:baccarat config ./config

USER baccarat

# tini is PID 1 so SIGTERM propagates correctly to asyncio
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "baccarat.app"]
