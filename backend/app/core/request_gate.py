"""Cooperative gate between user-facing requests and background lakehouse work.

WHY THIS EXISTS
---------------
The API process runs the auto-refresh pass (973 symbols: fetch -> Bronze ->
Silver -> Gold) in background threads. That work hammers the same MinIO
instance the read path uses, and it is CPU-heavy in pandas/pyarrow, so it
competes with user requests for both the GIL and the MinIO connection pool.

Measured impact on this machine:

    AAPL read   0.4s  ->   3.3s
    MSFT read   0.4s  ->  66.3s
    NVDA read   0.4s  ->  89.9s

The variance comes from WHERE the refresh pass happens to be: while it is
rebuilding a symbol it rewrites ~121 Silver + ~121 Gold monthly partitions,
and a read that lands in that window waits behind them. That is what made the
agent exceed the frontend's 90s timeout.

THE FIX
-------
The background work is not valuable WHILE somebody is waiting on the UI, so it
pauses. This module tracks how many user-facing requests are in flight; the
auto-refresh checks it before starting each symbol and waits while the user
is active.

The trade-off is deliberate: the refresh pass takes longer to finish (it idles
during interaction) but every interactive request becomes fast and
predictable. For a research demo that is exactly the right priority - nobody
is watching the refresh progress, but everybody is watching the UI.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_in_flight = 0
# Monotonic timestamp of the most recent request completion, used to avoid a
# thundering herd: after a request finishes the refresh waits a short grace
# period, so a user clicking through pages does not restart the rebuild storm
# on every click.
_last_request_at = 0.0

# How long the background work stays paused after the last request finished.
# Without this, a page that fires four requests in a row would let the
# refresh squeeze in between them and re-introduce the contention.
DEFAULT_GRACE_SECONDS = 2.0


def request_started() -> None:
    """Mark the beginning of a user-facing request."""
    global _in_flight
    with _lock:
        _in_flight += 1


def request_finished() -> None:
    """Mark the end of a user-facing request."""
    global _in_flight, _last_request_at
    with _lock:
        _in_flight = max(0, _in_flight - 1)
        _last_request_at = time.monotonic()


def in_flight() -> int:
    """Number of user-facing requests currently being served."""
    with _lock:
        return _in_flight


def user_active(grace_seconds: float = DEFAULT_GRACE_SECONDS) -> bool:
    """True while a request is running or just finished.

    The grace period keeps the background work paused for a moment after the
    last request, so a burst of page loads does not restart the rebuild
    storm between them.
    """
    with _lock:
        if _in_flight > 0:
            return True
        if grace_seconds <= 0:
            return False
        return (time.monotonic() - _last_request_at) < grace_seconds


def wait_while_user_active(
    poll_seconds: float = 0.25,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    stop_event: threading.Event | None = None,
    max_wait_seconds: float = 300.0,
) -> None:
    """Block while the user is active (or the stop event is set).

    Args:
        poll_seconds: how often to re-check.
        grace_seconds: quiet period after the last request.
        stop_event: when set, the wait returns immediately (shutdown).
        max_wait_seconds: hard cap, so a stuck counter can never wedge the
            background worker forever.
    """
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        if stop_event is not None and stop_event.is_set():
            return
        if not user_active(grace_seconds):
            return
        time.sleep(poll_seconds)
