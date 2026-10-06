#!/usr/bin/env sh
# Backend container entrypoint.
# Runs Alembic migrations (idempotent) and then execs the CMD.

set -e

echo "[entrypoint] Waiting for MySQL at ${MYSQL_HOST:-mysql}:${MYSQL_PORT:-3306}..."
python - <<'PY' || true
import os, socket, time
host, port = os.environ.get("MYSQL_HOST", "mysql"), int(os.environ.get("MYSQL_PORT", "3306"))
for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[entrypoint] MySQL reachable at {host}:{port}")
            break
    except OSError:
        time.sleep(2)
else:
    print("[entrypoint] WARNING: MySQL not reachable after 120s, continuing anyway")
PY

echo "[entrypoint] Running Alembic upgrade head..."
alembic upgrade head || echo "[entrypoint] alembic skipped (no migrations yet)"

echo "[entrypoint] Bootstrapping infrastructure (MinIO buckets + Kafka topics)..."
python scripts/bootstrap_infrastructure.py || echo "[entrypoint] bootstrap skipped"

echo "[entrypoint] Starting: $@"
exec "$@"
