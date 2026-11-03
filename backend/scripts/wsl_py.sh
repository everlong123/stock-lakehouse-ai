#!/bin/bash
# Run a Python script inside the WSL distro against the local MinIO lakehouse.
# Usage: ./scripts/wsl_py.sh scripts/diagnose_calendar_gaps.py AAPL MSFT
set -e
cd /mnt/d/School/kltn/stock-lakehouse-ai/backend
exec python3 "$@"
