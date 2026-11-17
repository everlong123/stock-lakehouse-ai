#!/usr/bin/env python3
"""Remove forecasts that no market data backs up.

WHY THIS SCRIPT EXISTS
----------------------
On 15/11/2026 the verification ledger (``predictions``) was found to hold
200 rows for the symbols ``TST0`` .. ``TST199``. Every one of them had
the same invented numbers - ``reference_close = 100.0``,
``predicted_close = 101.0`` - and every one of them was tagged
``source = "auto_eod_batch"``, the tag that means "the system published
this forecast before the session opened".

    10|Those 200 rows were counted by the Dashboard's "verified" number and
were indistinguishable from real published forecasts. They had been
written straight into MySQL: no Bronze partition, no Silver partition, no
Gold partition, no trained model - just rows.

WHAT IT REMOVES
---------------
Two groups, and the second is the important one:

1. **Test-fixture symbols.** Any symbol whose name starts with one of the
   markers in ``app.core.data_integrity.FABRICATED_SYMBOL_PREFIXES``
   (``TST``, ``TEST``, ``DEMO``, ``MOCK``, ``FAKE``, ``DUMMY``, ``SAMPLE``,
   ``PLACEHOLDER``, ``XXX``).

2. **Orphan symbols.** Any symbol in the table that has NO data in the
   Gold layer. A forecast is a statement about a real instrument: it is
   derived from that instrument's history and it is verified against
   that instrument's real close. A symbol that does not exist in the
   lakehouse has neither, so its row cannot be evidence of anything.
   This check is the strong one - it catches a fabricated row even when
   the name looks like a genuine ticker.

WHAT IT DOES NOT DO
-------------------
It does not "fix" a row, because there is no correct value to restore: a
forecast is the output of a model, and re-running the model for a symbol
with no history produces nothing. The honest state is an ABSENT row, so
the row is deleted rather than filled with a placeholder.

SAFETY
------
  * dry run by default; ``--apply`` is required to write
  * every removed row is reported, per symbol
  * ``--prefix-only`` restricts the check to the denylist and skips the
    Gold lookup (use it when the storage backend is down)
  * rows that carry a score (``actual_close IS NOT NULL``) are reported
    separately: a scored row means a real close was once matched to this
    forecast, which deserves a look before it is deleted

Run:
    python scripts/purge_fake_predictions.py
    python scripts/purge_fake_predictions.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.data_integrity import is_fabricated_symbol
from app.core.logging_config import get_logger, setup_logging
from app.database.models.prediction import Prediction
from sqlalchemy import select

logger = get_logger(__name__)


def _gold_symbols() -> set[str] | None:
    """Every symbol that has data in the Gold layer.

    Returns ``None`` when the storage backend cannot be reached, so the
    caller can fall back to the prefix check alone instead of silently
    treating an unreachable lakehouse as "no orphans".
    """
    try:
        from app.lakehouse.storage_factory import get_storage_backend

        storage = get_storage_backend()
        symbols: set[str] = set()
        for key in storage.list_objects("gold", "symbol="):
            name = str(key)
            if not name.startswith("symbol="):
                continue
            symbols.add(name.split("=", 1)[1].split("/", 1)[0])
        return symbols
    except Exception as exc:  # noqa: BLE001
        logger.warning("The Gold layer could not be read: %s", exc)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the rows (default: a dry run).",
    )
    parser.add_argument(
        "--prefix-only",
        action="store_true",
        help="Only use the test-fixture denylist; do not read the Gold layer.",
    )
    args = parser.parse_args()

    setup_logging()

    from app.database.repositories.prediction_repository import PredictionRepository
    from app.database.session import check_database_connection, get_session_factory
    if not check_database_connection():
        print("The database is unavailable. Nothing was changed.")
        return 1

    gold = None
    if not args.prefix_only:
        gold = _gold_symbols()
        if gold is None:
            print(
                "The Gold layer could not be read. Re-run with --prefix-only "
                "to use the denylist alone, or fix the storage backend."
            )
            return 1

    print("=" * 78)
    print("PURGE FORECASTS WITH NO MARKET DATA BEHIND THEM")
    print("=" * 78)
    print(f"mode          : {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"gold symbols  : {len(gold) if gold is not None else 'not read'}")
    print()

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)

        rows = repository.session.execute(select(Prediction)).scalars().all()
        print(f"rows in the table: {len(rows)}")
        print()

        reasons: Counter[str] = Counter()
        victims: list = []
        scored_victims: list = []

        for row in rows:
            if is_fabricated_symbol(row.symbol):
                reasons["test_fixture_symbol"] += 1
                victims.append(row)
            elif gold is not None and row.symbol not in gold:
                reasons["orphan_symbol"] += 1
                victims.append(row)
            else:
                continue
            if row.actual_close is not None:
                scored_victims.append(row)

        if not victims:
            print("Nothing to remove: every forecast is backed by real market data.")
            return 0

        print(f"{'symbol':<16} {'rows':>6} {'scored':>8}")
        print("-" * 78)
        per_symbol: Counter[str] = Counter()
        for row in victims:
            per_symbol[row.symbol] += 1
        for symbol, count in sorted(per_symbol.items()):
            scored = sum(1 for row in victims if row.symbol == symbol and row.actual_close is not None)
            print(f"{symbol:<16} {count:>6} {scored:>8}")
        print("-" * 78)
        print(f"{'TOTAL':<16} {len(victims):>6} {len(scored_victims):>8}")
        for reason, count in reasons.most_common():
            print(f"    {reason:<28} {count}")
        print()

        if scored_victims:
            print(
                "NOTE: some of these rows carry a score, which means a real "
                "closing price was matched to them at some point. They are "
                "listed above with a non-zero 'scored' count."
            )
            print()

        if not args.apply:
            print("DRY RUN - nothing was modified. Re-run with --apply")
            return 0

        for row in victims:
            session.delete(row)
        session.commit()

        print(f"DELETED {len(victims)} rows.")
        print(
            "Audit trail written to the console at "
            + datetime.now(timezone.utc).isoformat()
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
