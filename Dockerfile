FROM python:3.13-slim AS builder

ENV UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md /app/
COPY listenbrainz_lidarr_sync /app/listenbrainz_lidarr_sync
COPY schemas /app/schemas

RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /app /app

RUN useradd --create-home --home-dir /home/appuser --shell /usr/sbin/nologin --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["/app/.venv/bin/listenbrainz-lidarr-sync"]
