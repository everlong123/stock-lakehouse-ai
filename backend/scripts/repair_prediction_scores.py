"""Audit stored scores; optionally repair mismatches with a preserved snapshot."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from sqlalchemy import select
    from app.database.models.prediction import Prediction
    from app.database.models.prediction_revision import PredictionRevision
    from app.database.session import get_session_factory
    from app.services.forecast_scoring import score_forecast

    changes = []
    checked = 0
    with get_session_factory()() as session:
        rows = session.scalars(select(Prediction).where(Prediction.actual_close.isnot(None))).all()
        for row in rows:
            checked += 1
            expected = score_forecast(row, row.actual_close, row.scored_at)
            differences = {}
            for field in ("abs_error", "error_pct", "direction_correct"):
                before, after = getattr(row, field), expected[field]
                equal = before == after
                if before is not None and after is not None and field != "direction_correct":
                    # Existing MySQL FLOAT columns round stored prices/errors.
                    equal = math.isclose(float(before), float(after), rel_tol=2e-5, abs_tol=1e-5)
                if not equal:
                    differences[field] = {"before": before, "after": after}
            if not differences:
                continue
            changes.append({"id": row.id, "symbol": row.symbol, "model": row.model_name, "target_session": row.target_session.isoformat(), "differences": differences})
            if args.apply:
                snapshot = {
                    column.name: (value.isoformat() if isinstance(value, (date, datetime)) else value)
                    for column in Prediction.__table__.columns
                    if (value := getattr(row, column.name)) is not None
                }
                session.add(PredictionRevision(prediction_id=row.id, symbol=row.symbol, model_name=row.model_name,
                                               target_session=row.target_session, issued_at=row.created_at, payload=snapshot))
                for field in differences:
                    setattr(row, field, expected[field])
        if args.apply:
            session.commit()
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "applied": args.apply, "checked": checked, "mismatches": len(changes), "changes": changes}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "changes"}))


if __name__ == "__main__":
    main()
