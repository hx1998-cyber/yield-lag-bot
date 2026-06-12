# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip wheel \
 && pip wheel --wheel-dir /wheels .

FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 yieldlag \
 && useradd --system --uid 1000 --gid yieldlag --create-home --shell /bin/bash yieldlag

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels yield-lag-bot \
 && rm -rf /wheels

COPY --chown=yieldlag:yieldlag alembic.ini ./alembic.ini
COPY --chown=yieldlag:yieldlag migrations ./migrations
COPY --chown=yieldlag:yieldlag config ./config

USER yieldlag

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "yield_lag_bot.app"]
