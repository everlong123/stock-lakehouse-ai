"""Alembic environment.

Loads SQLAlchemy URL from app settings and points metadata at app.database.base.Base.
"""

from __future__ import annotations

import logging
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app.*` importable when running alembic from the project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database import models  # noqa: F401, E402  (registers all tables on Base)

config = context.config
if config.config_file_name is not None:
    # `fileConfig()` REPLACES the root logger's handlers and level with the
    # contents of alembic.ini's [loggers]/[handlers] sections - i.e. a single
    # console handler at level WARN. That is a hard problem here, because
    # alembic/env.py runs INSIDE the FastAPI lifespan:
    #
    #   app/main.py -> setup_logging()   (root: file + console handlers, INFO)
    #   app/main.py -> run_migrations()  -> alembic/env.py -> fileConfig()
    #
    # So the moment the migration ran, every log line the app produced after
    # that point was filtered out (INFO < WARN) and never reached the file
    # handler either. The symptom was a backend that clearly WAS fetching and
    # ingesting data, but logged nothing from app.* - no "AutoRefreshService
    # started", no progress lines, no pass summary. The auto-refresh service
    # looked dead while it was running.
    #
    # The fix is to let alembic configure its own loggers and then put the
    # application's root handlers back the way we found them.
    #
    # `disable_existing_loggers=False` alone is NOT enough: that flag only
    # stops existing loggers from being disabled, but fileConfig still
    # REPLACES the root handlers with alembic's console-only, WARN-level
    # configuration.
    _root = logging.getLogger()
    _saved_handlers = list(_root.handlers)
    _saved_level = _root.level

    fileConfig(config.config_file_name, disable_existing_loggers=False)

    if _saved_handlers:
        # Only restore when the app had already configured logging (the
        # in-process FastAPI path). Running `alembic` from the CLI has no
        # pre-existing handlers and must keep alembic's own console output.
        _root.handlers = _saved_handlers
        _root.setLevel(_saved_level)

config.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
