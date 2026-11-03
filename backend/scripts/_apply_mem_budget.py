"""Append the memory-budget settings to .env.local (UTF-8 safe)."""
import pathlib

p = pathlib.Path(".env.local")
t = p.read_text(encoding="utf-8")

block = """
# ── Memory budget cho CPU-bound job pool ─────────────────────────────────────
# Máy này KHÔNG có pagefile: commit limit = RAM thật (31.8GB). Mỗi worker
# pool giữ ~700MB (pandas + lịch sử 1 mã), nên pool tự thu nhỏ theo RAM
# còn trống để không bị Windows giết (Event 2004 "low virtual memory").
HEAVY_WORKER_MEMORY_MB=700
HEAVY_RESERVE_FOR_HOST_MB=4096
HEAVY_POOL_SIZE=2
HEAVY_BACKGROUND_POOL_SIZE=3
"""

if "HEAVY_WORKER_MEMORY_MB" not in t:
    t = t.rstrip() + "\n" + block

p.write_text(t, encoding="utf-8")
print([l for l in t.splitlines() if l.startswith(("HEAVY", "AUTO_REFRESH"))])
