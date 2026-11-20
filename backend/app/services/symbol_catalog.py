"""Cached inventory of instruments actually present in the lakehouse."""

from pathlib import Path
import threading
import time

from app.lakehouse.storage_factory import get_storage_backend

_lock = threading.Lock()
_symbols: frozenset[str] = frozenset()
_expires_at = 0.0


def stored_symbols() -> frozenset[str]:
    """Include archived tickers without treating arbitrary prose as a ticker.

    Cache the top-level Bronze listing for five minutes. A storage failure
    leaves the curated universe usable and retries after thirty seconds.
    """
    global _symbols, _expires_at
    with _lock:
        if time.monotonic() < _expires_at:
            return _symbols
        try:
            storage = get_storage_backend()
            if storage.backend_name == "local":
                root = Path(storage.root) / "bronze"
                found = {
                    p.name.split("=", 1)[1].upper()
                    for p in root.iterdir()
                    if p.is_dir() and p.name.startswith("symbol=") and any(p.rglob("*.parquet"))
                } if root.exists() else set()
            else:
                objects = storage.client.list_objects(
                    storage._bucket("bronze"), prefix="symbol=", recursive=False
                )
                found = {
                    obj.object_name.split("/", 1)[0].split("=", 1)[1].upper()
                    for obj in objects
                    if obj.object_name and obj.object_name.startswith("symbol=")
                }
            _symbols = frozenset(found - {""})
            _expires_at = time.monotonic() + 300
        except Exception:
            _expires_at = time.monotonic() + 30
        return _symbols
