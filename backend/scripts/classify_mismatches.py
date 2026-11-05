"""Classify the symbols the verifier flagged as FAIL.

Two very different causes produce the same "[FAIL] ... 1 mismatch" line:

* A **corporate action** (bonus share, stock split) that the provider applies
  to its *adjusted* close but not to the *raw* close. The stored history is
  correct; only the comparison is wrong, because the verifier compares the
  stored raw close against the provider's raw close while the provider
  restates the OLD bars.
* A genuinely **stale or wrong** stored value.

This script re-fetches each failing symbol and reports the ratio between the
stored close and the live close, plus whether the ratio is a clean
corporate-action factor (1.15, 1.5, 1.1, ...) or something arbitrary.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/classify_mismatches.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.core.logging_config import setup_logging  # noqa: E402

# The 22 symbols the full-universe verification flagged on 2026-11-04.
DEFAULT_SYMBOLS = [
    "AZN.L", "BP.L", "DG.PA", "DGE.L", "EL.PA", "ENEL.MI", "ENGI.PA",
    "ENI.MI", "EOAN.DE", "GLE.PA", "HSBA.L", "PARA", "PC1", "RIO.L",
    "SAF.PA", "SAN.PA", "SAP.DE", "SHEL.L", "STLAM.MI", "TTE.PA",
    "VIV.PA", "VOW3.DE",
]

# Split factors seen on Vietnamese/European listings. Yahoo reports these as
# "115:100" style ratios.
CORP_ACTION_FACTORS = (1.15, 1.1, 1.05, 1.2, 1.25, 1.5, 2.0, 3.0, 0.5, 0.75)


def main() -> int:
    setup_logging()

    from app.data_sources.factory import get_data_provider
    from app.lakehouse.bronze import BronzeLayer

    provider = get_data_provider("yahoo_http")
    bronze = BronzeLayer()

    print(f"{'symbol':<12} {'rows':>5} {'ratio med':>10} {'ratio min':>10} "
          f"{'ratio max':>10}  verdict")
    print("-" * 78)

    corporate_action: list[str] = []
    genuinely_wrong: list[str] = []
    no_data: list[str] = []

    for symbol in DEFAULT_SYMBOLS:
        try:
            live = provider.get_historical_data(
                symbol,
                start=datetime(2016, 1, 1, tzinfo=timezone.utc),
                end=datetime.now(timezone.utc),
                interval="1d",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"{symbol:<12} provider error: {exc}")
            no_data.append(symbol)
            continue

        stored = bronze.read(symbol)
        if stored.empty or live.empty:
            print(f"{symbol:<12} no data in one side")
            no_data.append(symbol)
            continue

        stored["timestamp"] = pd.to_datetime(stored["timestamp"], utc=True)
        live["timestamp"] = pd.to_datetime(live["timestamp"], utc=True)
        merged = stored.merge(
            live[["timestamp", "close"]].rename(columns={"close": "live_close"}),
            on="timestamp",
            how="inner",
        )
        if merged.empty:
            print(f"{symbol:<12} no overlapping sessions")
            no_data.append(symbol)
            continue

        ratio = (merged["close"] / merged["live_close"]).replace(
            [float("inf"), float("-inf")], pd.NA
        ).dropna()
        if ratio.empty:
            print(f"{symbol:<12} no usable ratio")
            no_data.append(symbol)
            continue

        median = float(ratio.median())
        spread = float(ratio.max() - ratio.min())
        verdict = "OK"
        if median > 1.0005 or median < 0.9995:
            close_to_action = any(abs(median - f) < 0.001 for f in CORP_ACTION_FACTORS)
            verdict = "CORP-ACTION" if close_to_action else "WRONG SCALE"
            (corporate_action if close_to_action else genuinely_wrong).append(symbol)
        elif spread > 0.001:
            verdict = "PARTIAL (some bars differ)"
            genuinely_wrong.append(symbol)
        else:
            verdict = "OK (tolerance)"

        print(f"{symbol:<12} {len(merged):>5} {median:>10.6f} {float(ratio.min()):>10.6f} "
              f"{float(ratio.max()):>10.6f}  {verdict}")

    print()
    print(f"corporate action ({len(corporate_action)}): {corporate_action}")
    print(f"genuinely wrong  ({len(genuinely_wrong)}): {genuinely_wrong}")
    print(f"no data          ({len(no_data)}): {no_data}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
