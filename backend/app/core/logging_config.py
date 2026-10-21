"""Centralized logging configuration with rotating file handler."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

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


def setup_logging() -> None:
    """Configure root and application loggers once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_path: Path = settings.log_file_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
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
