#!/usr/bin/env python3
"""Remove forecasts whose price could not exist on an exchange.

WHY THIS SCRIPT EXISTS
----------------------
On 15/11/2026 the verification ledger (``predictions``) was audited after
the reported "mean error" of the whole pool turned out to be 26.385% -
a number no real forecasting system produces. The cause was NOT the small
denominators everyone assumed. It was THIS:

    * Nineteen rows carried a NEGATIVE predicted price:

          LCID   reference   3.61   predicted    -4.09
          ACH    reference   0.86   predicted    -0.114
          SOXS   reference  45.72   predicted  -359,121,248
          UVXY   reference  17.35   predicted  -33,570.79
          SQQQ   reference  10.00   predicted     -647.88

    * One symbol - ``PARA`` - held 99,993% of the total absolute error of
      all 44.676 verified rows. Its Bronze/Gold history spans four reverse
      splits (1:50 on 19/09/2024, 1:10 on 08/07/2025, 1:20 on 08/05/2026,
      1:10 on 27/10/2026), so the price series runs from ~101.500 down to
      0,104. A price-LEVEL regression fitted on that series extrapolated
      off the end of it: predictions of 242.751 and 329.139 against an
      actual of 0,101 - a single-row error of +337.153.925%.

WHAT IT REMOVES
---------------
Rows whose forecast price is physically impossible:

1. **A non-positive forecast price.** No exchange prints a negative price.
2. **A forecast more than ``MAX_PREDICTION_REFERENCE_FACTOR`` (100x) away
   from its own reference price.** That is the signature of a model
   fitted across a price-scale break. A tighter bound would reject real
   moves: PARA itself traded 0,104 -> 0,164 -> 0,319 -> 2,72 inside three
   sessions in November 2026.

It ALSO reports (but does not delete) the rows of symbols whose Gold
history contains a price-scale discontinuity, so the operator can re-train
those symbols on a repaired history - see ``app/lakehouse/scale_repair.py``.

WHY IT DELETES RATHER THAN FIXES
--------------------------------
A forecast is the output of a model. There is no correct value to
restore for a session that has already happened: the honest state is an
ABSENT row, and the accuracy report then counts one fewer verified
forecast instead of one absurd one.

SAFETY
------
  * dry run by default; ``--apply`` is required to write
  * every removed row is listed with its numbers
  * ``--keep-impossible`` reports the impossible rows without deleting
    them, for when a human wants to look first

Run:
    python scripts/purge_impossible_predictions.py
    python scripts/purge_impossible_predictions.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.data_integrity import (
    MAX_PREDICTION_REFERENCE_FACTOR,
    is_impossible_price,
)
from app.core.logging_config import get_logger, setup_logging
from app.database.models.prediction import Prediction
from sqlalchemy import select

logger = get_logger(__name__)


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
        "--keep-impossible",
        action="store_true",
        help="Only report; do not delete anything.",
    )
    args = parser.parse_args()

    setup_logging()

    from app.database.session import check_database_connection, get_session_factory

    if not check_database_connection():
        print("The database is unavailable. Nothing was changed.")
        return 1

    print("=" * 78)
    print("PURGE FORECASTS WITH A PHYSICALLY IMPOSSIBLE PRICE")
    print("=" * 78)
    print(f"mode            : {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"max ref factor  : {MAX_PREDICTION_REFERENCE_FACTOR}x")
    print()

    session = get_session_factory()()
    try:
        rows = session.execute(select(Prediction)).scalars().all()
        print(f"rows in the table: {len(rows)}")
        print()

        victims = [
            row
            for row in rows
            if is_impossible_price(row.predicted_close, row.reference_close)
        ]
        if not victims:
            print("Nothing to remove: every forecast carries a printable price.")
            return 0

        reasons: Counter[str] = Counter()
        for row in victims:
            if row.predicted_close is not None and float(row.predicted_close) <= 0:
                reasons["negative_or_zero_price"] += 1
            else:
                reasons["scale_mismatch"] += 1

        print(f"{'symbol':<14} {'session':<12} {'reference':>14} {'predicted':>18} {'scored':>7}")
        print("-" * 78)
        for row in sorted(victims, key=lambda r: (r.symbol, r.target_session)):
            reference = "n/a" if row.reference_close is None else f"{row.reference_close:,.4f}"
            print(
                f"{row.symbol:<14} {str(row.target_session):<12} {reference:>14} "
                f"{row.predicted_close:>18,.4f} {'yes' if row.actual_close is not None else '-':>7}"
            )
        print("-" * 78)
        print(f"{'TOTAL':<14} {'':<12} {'':<14} {len(victims):>18}")
        for reason, count in reasons.most_common():
            print(f"    {reason:<28} {count}")
        print()

        if args.keep_impossible or not args.apply:
            print(
                "DRY RUN - nothing was modified. "
                "Re-run with --apply to delete these rows."
            )
            return 0

        for row in victims:
            session.delete(row)
        session.commit()

        print(f"DELETED {len(victims)} rows.")
        print("Audit trail written to the console at "
              + datetime.now(timezone.utc).isoformat())
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
