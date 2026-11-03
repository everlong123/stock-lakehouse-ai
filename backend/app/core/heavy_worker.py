"""Run CPU-bound lakehouse jobs in a separate PROCESS, not a thread.

WHY THIS EXISTS
---------------
The API process runs two kinds of work at the same time:

  * the **auto-refresh pass** (973 symbols: fetch -> Bronze -> Silver -> Gold),
    which is pure-Python/pandas work spread over ~20 worker threads, and
  * the **interactive request path** (the agent, the dashboard, the charts).

Both are CPU-bound Python, so they share ONE GIL. CPython releases the GIL
every ``sys.getswitchinterval()`` (5 ms by default) and hands it to whichever
thread is waiting - but with 20 refresh threads each doing pandas work, a
request thread gets a small slice of the total CPU time.

The measured consequence was severe:

    walk-forward validation, idle process ............ 2.2 s
    walk-forward validation, refresh running ......... 13.3 s   (6x)
    walk-forward validation, real server load ........ 96  s   (40x)

The 96 s case is the one that broke the UI: the agent's 75 s server deadline
fired and the browser showed "Yêu cầu mất quá lâu (>90s)". The stack dump at
the moment of the timeout showed the request thread sitting inside
``pandas.core.series.dropna`` - i.e. it was RUNNING, just starved of CPU.

A thread cannot fix this (threads share the GIL), but a PROCESS can: a child
process has its own interpreter and its own GIL, so the walk-forward gets a
full core while the refresh keeps its share of the parent's GIL.

TWO POOLS, NOT ONE
------------------
The interactive path and the background refresh get SEPARATE pools on
purpose. A shared pool would let a burst of refresh rebuilds occupy every
worker and leave the user's request queued behind them - the exact failure
mode we are fixing. The interactive pool is small and always has capacity; the
background pool is larger and absorbs the refresh throughput.

    interactive  HEAVY_POOL_SIZE          (default 2)
    background   HEAVY_BACKGROUND_POOL_SIZE (default 4)
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, Callable

# Importing `app.core.config` loads `.env.local` into `os.environ`, which is
# where the HEAVY_* settings below come from. Without this import the module
# would read the environment BEFORE `.env.local` was applied and silently fall
# back to the built-in defaults.
from app.core.config import settings as _settings  # noqa: F401  (side effect: loads .env.local)

logger = logging.getLogger(__name__)

# ── Memory budget ───────────────────────────────────────────────────────────
#
# WHY THIS EXISTS
# ---------------
# This host has NO Windows pagefile (AutomaticManagedPagefile=False), so the
# commit limit equals physical RAM (31.8 GB). When the commit charge gets
# close to that limit, Windows raises "low virtual memory condition" events
# and, if a process tries to allocate past it, the allocation FAILS and the
# process is killed - no swap, no warning, just an abrupt death.
#
# The Windows event log recorded exactly that on the night this was written:
#
#   Event 2004, 03:07:15 - "low virtual memory condition"
#     vmmemWSL   consumed 12.9 GB
#     python.exe consumed  1.67 GB
#     python.exe consumed  0.74 GB
#
#   Event 1000, 02:38:55 - wslservice.exe / wslrelay.exe faulted
#
# The worker processes were the victims: the refresh pool holds 4 children
# that each load a FULL symbol history into pandas, and the parent process
# is already 1.6 GB. The children were killed mid-rebuild, which broke the
# ProcessPoolExecutor, and from then on every rebuild failed with
# "the process pool is not usable anymore".
#
# THE FIX HAS TWO HALVES:
#
#  1. Bound the pool sizes by the memory that is actually free, not by a
#     hardcoded number. A worker is only spawned if there is room for it.
#  2. Cap how many rebuilds run at once, so N children never coexist.
#
# Each worker is budgeted at ~700 MB (pandas + pyarrow imports ~130 MB, a
# full symbol history in a DataFrame ~400 MB, the indicator columns ~150 MB).
WORKER_MEMORY_MB = int(os.getenv("HEAVY_WORKER_MEMORY_MB", "700"))

# How much free RAM (in MB) must remain for Windows itself. The desktop,
# Cursor, the antivirus and the browser all need headroom; below this the
# machine starts swapping hard - and with no pagefile, thrashing means
# crashes.
RESERVE_FOR_HOST_MB = int(os.getenv("HEAVY_RESERVE_FOR_HOST_MB", "4096"))


def _available_memory_mb() -> int:
    """Free physical RAM on this machine, in MB (0 if it cannot be read)."""
    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return 0
        return int(stat.ullAvailPhys // (1024 * 1024))
    except Exception:  # noqa: BLE001 - never let this break a job
        return 0


def _affordable_workers(desired: int) -> int:
    """How many workers we can afford right now, given free RAM."""
    available = _available_memory_mb()
    if available <= 0:
        return desired
    budget = available - RESERVE_FOR_HOST_MB
    if budget <= 0:
        # Nothing spare: still allow ONE worker, because the alternative is
        # doing nothing at all, and one worker is a small, bounded cost.
        return 1
    affordable = budget // WORKER_MEMORY_MB
    return max(1, min(desired, int(affordable)))


# Interactive pool: serves user-visible requests (the agent's backtest and
# walk-forward tools).
#
# Memory: each child re-imports pandas (~130 MB RSS) and holds one symbol's
# history. The host has no pagefile, so the count is kept modest - and it is
# clamped further by the available-RAM check in `_affordable_workers`.
INTERACTIVE_POOL_SIZE = int(os.getenv("HEAVY_POOL_SIZE", "2"))

# Background pool: serves the auto-refresh rebuilds. Sized to match
# AUTO_REFRESH_REBUILD_WORKERS so the refresh keeps its throughput - but
# again clamped by the available RAM.
BACKGROUND_POOL_SIZE = int(os.getenv("HEAVY_BACKGROUND_POOL_SIZE", "4"))

_pools: dict[str, ProcessPoolExecutor] = {}
_pool_lock = threading.Lock()


def _build_pool(size: int) -> ProcessPoolExecutor:
    # The "spawn" context is required on Windows: a forked child would
    # inherit the parent's threads, including the MinIO connection pool and
    # the refresh workers, which is a recipe for deadlocks.
    context = multiprocessing.get_context("spawn")
    return ProcessPoolExecutor(max_workers=size, mp_context=context)


def get_pool(name: str = "interactive") -> ProcessPoolExecutor:
    """Return the named process pool, creating it on first use.

    The pool is sized by what the machine can actually afford RIGHT NOW,
    not by a hardcoded number. See ``_affordable_workers`` for why that
    matters on a box with no pagefile.
    """
    with _pool_lock:
        pool = _pools.get(name)
        if pool is None:
            desired = INTERACTIVE_POOL_SIZE if name == "interactive" else BACKGROUND_POOL_SIZE
            size = _affordable_workers(desired)
            if size < desired:
                logger.warning(
                    "Heavy-job pool '%s' limited to %d/%d workers: only %d MB of RAM "
                    "free (each worker is budgeted at %d MB, %d MB reserved for the host).",
                    name,
                    size,
                    desired,
                    _available_memory_mb(),
                    WORKER_MEMORY_MB,
                    RESERVE_FOR_HOST_MB,
                )
            pool = _build_pool(size)
            _pools[name] = pool
            logger.info("Heavy-job pool '%s' started (workers=%d)", name, size)
        return pool


def _discard_pool(name: str) -> None:
    """Drop a broken pool so the next call builds a fresh one."""
    with _pool_lock:
        pool = _pools.pop(name, None)
    if pool is None:
        return
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:  # noqa: BLE001 - a broken pool may raise on shutdown
        pass


def shutdown_pool() -> None:
    """Tear every pool down (used on application shutdown)."""
    with _pool_lock:
        for name, pool in list(_pools.items()):
            pool.shutdown(wait=False, cancel_futures=True)
            logger.info("Heavy-job pool '%s' stopped", name)
        _pools.clear()


def run_in_process(
    func: Callable[..., Any],
    *args: Any,
    pool_name: str = "interactive",
    **kwargs: Any,
) -> Any:
    """Run ``func`` in a child process and return its result.

    ``func`` must be a module-level callable (picklable) and its arguments
    must be picklable too. Exceptions raised inside the child are
    re-raised in the caller, so the error handling does not change.

    A POOL THAT DIED IS REBUILT
    ----------------------------
    ``ProcessPoolExecutor`` is permanently broken once a worker dies
    abruptly: every later ``submit()`` raises
    ``BrokenProcessPool("the process pool is not usable anymore")``. That
    is exactly what happened when the OS killed the workers under memory
    pressure - and because the broken pool was cached, EVERY subsequent
    rebuild failed too, so the refresh could never recover on its own.

    Here a broken pool is discarded and the job is retried once on a fresh
    pool. Only if that also fails does the error reach the caller, which
    falls back to running the job in-process.
    """
    last_exc: Exception | None = None
    for attempt in (1, 2):
        pool = get_pool(pool_name)
        try:
            future = pool.submit(func, *args, **kwargs)
            return future.result()
        except BrokenProcessPool as exc:
            # The worker died (usually OOM-killed). The pool is unusable.
            last_exc = exc
            logger.warning(
                "Heavy-job pool '%s' broke (attempt %d/2): %s",
                pool_name,
                attempt,
                exc,
            )
            _discard_pool(pool_name)
            continue
    raise last_exc if last_exc is not None else RuntimeError("heavy job failed")
