# Multi-stage build for the FastAPI backend.
# Stage 1: builder - install dependencies into a venv we can copy across.
# Stage 2: runtime - slim image with only the venv + source.

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# OS deps for wheels (pandas/pyarrow compile against these on slim).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_HOME=/app

# Minimal runtime libs (PyMySQL + cryptography + curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app

WORKDIR ${APP_HOME}

# Pre-create writable dirs for runtime user (non-root).
RUN mkdir -p ${APP_HOME}/logs ${APP_HOME}/data ${APP_HOME}/data/models \
    && chown -R app:app ${APP_HOME}

# Copy the prepared venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Copy the application source.
COPY --chown=app:app app ${APP_HOME}/app
COPY --chown=app:app scripts ${APP_HOME}/scripts
COPY --chown=app:app tests ${APP_HOME}/tests
COPY --chown=app:app entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown app:app /entrypoint.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
