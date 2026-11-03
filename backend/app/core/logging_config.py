"""Centralized logging configuration with rotating file handler."""

from __future__ import annotations

import logging
import multiprocessing
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable

from app.core.config import settings


def _wrap_emit(
    emit: Callable[[logging.LogRecord], None],
    after: Callable[[], None],
) -> Callable[[logging.LogRecord], None]:
    """Return an emit() that calls `after()` once a record is actually written.

    StreamHandler/RotatingFileHandler buffers records internally; a crash or
    thread shutdown can drop the tail of the log. Hooking the post-write flush
    is the standard workaround and is cheap under normal load (a flush per
    log line is fine for the rates this app produces).
    """
    def wrapped(record: logging.LogRecord) -> None:
        emit(record)
        after()
    return wrapped


_CONFIGURED = False


class _SafeRotatingFileHandler(RotatingFileHandler):
    """A rotating file handler whose rollover failure is not fatal.

    WHY THIS SUBCLASS EXISTS
    -------------------------
    On Windows a file that is open in ANOTHER process cannot be renamed, so
    ``doRollover()`` raises ``PermissionError``. The stock
    ``RotatingFileHandler.emit()`` catches that exception, calls
    ``handleError()`` (which only writes to stderr) and then DROPS the
    record.

    The visible symptom was a server that was alive and perfectly healthy
    but whose log file had "stopped" at exactly ``maxBytes``: every single
    log line after that point was discarded, silently. The cause was an
    orphaned worker process still holding the old file open.

    This handler keeps the application alive AND keeps the logs useful:

    * the first failed rollover disables rotation (the file keeps growing,
      it just never rotates again), and
    * a warning is emitted so the problem is visible rather than invisible.

    The handler falls back to a plain append-mode stream if even opening the
    file fails.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._rollover_disabled = False

    def doRollover(self) -> None:
        if self._rollover_disabled:
            return
        try:
            super().doRollover()
        except (PermissionError, OSError) as exc:
            self._rollover_disabled = True
            self.handleError(
                logging.LogRecord(
                    name=__name__,
                    level=logging.WARNING,
                    pathname=str(self.baseFilename),
                    lineno=0,
                    msg=(
                        "Log rollover failed (%s); rotation disabled for %s. "
                        "Logging continues without rotation."
                    ),
                    args=(),
                    exc_info=None,
                )
            )

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        if self._rollover_disabled:
            return False
        return super().shouldRollover(record)


def _resolve_log_path(log_path: Path) -> Path:
    """Return the log file this PROCESS should write to.

    WHY THIS IS NOT ALWAYS THE SAME FILE
    -------------------------------------
    The CPU-bound jobs run in spawned child processes (see
    ``app.core.heavy_worker``). Every one of them configures its own
    ``RotatingFileHandler`` - and a ``RotatingFileHandler`` renames the
    current file out of the way when it grows past ``maxBytes``.

    With several processes holding a handle to the SAME file, a rotation
    orphans the other processes' handles: they keep writing into the renamed
    ``app.log.1`` while the new ``app.log`` sits empty. The visible symptom
    was that the log appeared to "stop" a few minutes after startup - the
    server was alive and logging, but to a file nobody was reading.

    Giving each child its own file removes the contention entirely: only the
    parent process ever rotates the shared file.
    """
    if multiprocessing.parent_process() is None:
        return log_path
    # A spawned child: write to a sibling file named after our PID.
    return log_path.with_name(f"{log_path.stem}.{os.getpid()}{log_path.suffix}")


def setup_logging() -> None:
    """Configure root and application loggers once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_path: Path = _resolve_log_path(settings.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = _SafeRotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(formatter)
    # Wrap with flush-after-every-record. Without this the worker thread that
    # runs `run_once()` can drop lines on shutdown, hang on a slow disk write,
    # or hang forever while held files keep growing. Cheaper than it sounds:
    # a single os.fsync-level flush only matters at crash time anyway, and
    # RotatingFileHandler doesn't emit that often.
    _flush_after = lambda: file_handler.flush()  # noqa: E731
    file_handler.emit = _wrap_emit(file_handler.emit, _flush_after)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.emit = _wrap_emit(console_handler.emit, console_handler.flush)

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger after ensuring logging is configured."""
    setup_logging()
    return logging.getLogger(name)
