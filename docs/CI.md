# CI / CD

This document explains the GitHub Actions setup for the Stock Lakehouse AI
project and the rationale behind the disabled-schedule workflow shipped in
`.github/workflows/daily-ingest.yml`.

## Workflows

### `Daily Stock Ingest` — currently disabled

- **File**: `.github/workflows/daily-ingest.yml`
- **Schedule** (currently inert): every day at 11:00 UTC (18:00 ICT)
- **Manual trigger**: Action tab → "Daily Stock Ingest" → Run workflow

What it does:

1. Provisions an Ubuntu runner.
2. Installs the backend Python dependencies (cached via `actions/setup-python`).
3. Verifies that the developer's MinIO instance is reachable through an
   `ngrok` tunnel (URL stored in the repo secret `MINIO_NGROK_URL`).
4. Runs `python -m scripts.ingest_all --interval 1d --lookback 30` to
   incrementally refresh the Bronze/Silver/Gold tables in MinIO with the
   latest OHLCV bars from Yahoo Finance.

Why the schedule is currently disabled (job-level `if: false`):

- The CI runner is a cloud-hosted Ubuntu image. It cannot reach
  `minio:9000` on the developer's WSL2 instance unless that MinIO is
  exposed through a public tunnel. We already configured an
  `ngrok tcp 9000` tunnel for this purpose, plus the four required
  GitHub Actions secrets (`MINIO_NGROK_URL`, `MINIO_HOST`,
  `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`).
- However, the developer's workstation is **not online 24/7**. When
  the laptop is off or ngrok is not running, the scheduled run
  reliably fails with one of:
  - `MINIO_NGROK_URL secret is empty` — when the secret was never configured.
  - `Failed to connect to <ngrok-host>` — when the tunnel is down.
- The first scheduled run (2026-10-17 14:04 UTC) failed for exactly
  this reason and has been the only auto-trigger since the project
  began.

Because the local Docker Compose stack (`up-all`) already keeps the
Bronze/Silver/Gold tables warm via the in-app "Refresh" button and the
automated `auto-refresh` background service, there is no functional
gap while the CI schedule is disabled.

### How to demo the CI workflow manually (e.g. for the KLTN defense)

1. Make sure the laptop is online and the local stack is up:

   ```bash
   docker compose --profile all up -d
   ```

2. Start the ngrok tunnel in another terminal:

   ```bash
   ngrok tcp 9000
   ```

   Copy the printed `tcp://...` URL and paste it into the GitHub repo
   **Settings → Secrets and variables → Actions** as
   `MINIO_NGROK_URL` (the value should be the bare `hostname:port`,
   without the `tcp://` prefix and without trailing `/`).

3. Trigger the workflow manually:

   - Open the GitHub Actions tab → **Daily Stock Ingest**.
   - Click **Run workflow** → **Run workflow** on `main`.

4. To re-enable the daily schedule, remove the `if: false` line on
   the `ingest` job in `.github/workflows/daily-ingest.yml` and
   commit. The schedule will pick up on the next cron tick.

### Required GitHub repository secrets

| Secret | Example value | Purpose |
| --- | --- | --- |
| `MINIO_NGROK_URL` | `4.tcp.ngrok.io:12345` | Public tunnel to the local MinIO service. |
| `MINIO_HOST`       | `4.tcp.ngrok.io`         | Hostname (without port) used by the backend. |
| `MINIO_ACCESS_KEY` | `minioadmin`             | MinIO root user. |
| `MINIO_SECRET_KEY` | `<strong-password>`      | MinIO root password. |

All four must be present for the workflow to succeed once re-enabled.

## Local "CI" alternative

If you want a hands-off data refresh without depending on GitHub Actions
at all, the project already ships with two local options:

- **In-app auto-refresh** (`app/services/auto_refresh.py`): polls a
  configurable list of US EOD symbols and pushes them into the Kafka
  raw topic on a fixed interval (default 6 hours).
- **Stream-based warmup** (`backend/scripts/`): one-shot backfills
  across all Bronze/Silver/Gold tables.

Both run inside the `backend` container, so as long as
`docker compose --profile all up -d` is alive, the lakehouse is kept
fresh even when the developer is away.
