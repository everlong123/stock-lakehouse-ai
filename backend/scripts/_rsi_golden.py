"""Golden test: the vectorised RSI strategy must match the original pandas version.

The original implementation was:

    signal = pd.Series(0.0, index=frame.index, dtype=float)
    signal.loc[values < lower] = 1.0
    signal.loc[values > upper] = -1.0
    previous = signal.replace(0.0, np.nan).ffill().shift(1)
    crossings = signal.where(signal.ne(previous), 0.0).fillna(0.0)
    return crossings.clip(-1.0, 1.0)

This script re-implements that EXACTLY and compares it, row by row, against
the new numpy implementation over several symbols and parameter sets.
"""
import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd

from app.backtesting.strategies.rsi_strategy import RSIStrategy
from app.indicators.rsi import rsi
from app.services.market_service import _load_symbol_frame


def original_generate_signals(frame, parameters):
    period = int(parameters.get("rsi_period", 14))
    lower = float(parameters.get("lower_threshold", 30))
    upper = float(parameters.get("upper_threshold", 70))
    values = rsi(frame["close"], period)
    signal = pd.Series(0.0, index=frame.index, dtype=float)
    signal.loc[values < lower] = 1.0
    signal.loc[values > upper] = -1.0
    previous = signal.replace(0.0, np.nan).ffill().shift(1)
    crossings = signal.where(signal.ne(previous), 0.0).fillna(0.0)
    return crossings.clip(-1.0, 1.0)


failures = 0
checked = 0
for symbol in ["AAPL", "MSFT", "ADS.DE", "VNM", "VCB"]:
    try:
        frame, _ = _load_symbol_frame(symbol)
    except Exception as exc:
        print("skip %s (%s)" % (symbol, exc))
        continue
    if frame.empty:
        print("skip %s (empty)" % symbol)
        continue
    for params in (
        {},
        {"rsi_period": 14, "lower_threshold": 30, "upper_threshold": 70},
        {"rsi_period": 7, "lower_threshold": 25, "upper_threshold": 75},
        {"rsi_period": 21, "lower_threshold": 40, "upper_threshold": 60},
    ):
        expected = original_generate_signals(frame, params)
        actual = RSIStrategy(parameters=params).generate_signals(frame)
        checked += 1
        if len(expected) != len(actual):
            print("MISMATCH length %s %s" % (symbol, params))
            failures += 1
            continue
        diff = (expected.to_numpy() != actual.to_numpy()).sum()
        if diff:
            failures += 1
            print("MISMATCH %s %s -> %d differing rows" % (symbol, params, diff))
            idx = np.nonzero(expected.to_numpy() != actual.to_numpy())[0][:5]
            for i in idx:
                print("   row %d expected=%s actual=%s" % (i, expected.iloc[i], actual.iloc[i]))
        else:
            non_zero = int((expected.to_numpy() != 0).sum())
            print("OK %-7s %-52s rows=%d signals=%d" % (symbol, params, len(expected), non_zero))

print()
print("checked %d combinations, %d mismatches" % (checked, failures))
sys.exit(1 if failures else 0)
