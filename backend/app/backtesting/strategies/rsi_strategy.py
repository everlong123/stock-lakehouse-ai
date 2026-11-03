"""RSI threshold strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.backtesting.strategy_base import BaseStrategy
from app.indicators.rsi import rsi


class RSIStrategy(BaseStrategy):
    """Buy when RSI drops below the lower threshold. Sell when RSI exceeds the upper threshold."""

    name = "rsi_strategy"

    def generate_signals(self, frame: pd.DataFrame) -> pd.Series:
        period = int(self.parameters.get("rsi_period", 14))
        lower = float(self.parameters.get("lower_threshold", 30))
        upper = float(self.parameters.get("upper_threshold", 70))
        values = rsi(frame["close"], period)

        # Everything below works on plain numpy arrays instead of pandas
        # objects.
        #
        # WHY: the walk-forward validator calls `generate_signals` TWICE per
        # window (train + test) over ~175 windows, so this function is the
        # single hottest piece of code in the whole agent path. The original
        # pandas version chained `replace` -> `ffill` -> `shift` -> `where` ->
        # `fillna` -> `clip`, and every one of those steps allocated a fresh
        # Series and a fresh BlockManager. Profiling showed 2.0s of a 4.5s
        # walk-forward run inside this one function, and because it is pure
        # Python it competes for the GIL with the background refresh pass -
        # which is what turned a 2s backtest into a 75s timeout.
        #
        # The numpy version below produces BIT-IDENTICAL signals (the golden
        # test `scripts/_canonical_golden.py` and the walk-forward golden
        # comparison both verify this) but allocates a handful of arrays
        # instead of a dozen pandas objects.
        raw = values.to_numpy(dtype=float, copy=False)
        size = raw.shape[0]
        if size == 0:
            return pd.Series([], index=frame.index, dtype=float)

        signal = np.zeros(size, dtype=float)
        signal[raw < lower] = 1.0
        signal[raw > upper] = -1.0

        # `previous` = the last NON-ZERO signal strictly before this row.
        #
        # The original code was
        #     previous = signal.replace(0.0, np.nan).ffill().shift(1)
        # which carries the last non-zero signal forward and shifts it by one
        # row. NaN in `previous` means "no prior position", and pandas' `.ne`
        # treats NaN as different from any number - so a row with no prior
        # signal always counts as a crossing.
        previous = np.full(size, np.nan, dtype=float)
        last = np.nan
        for index in range(size):
            previous[index] = last
            value = signal[index]
            if value != 0.0:
                last = value

        # Keep only threshold crossings to avoid repeated orders on every bar.
        crossings = np.where(signal != previous, signal, 0.0)
        crossings = np.nan_to_num(crossings, nan=0.0)
        crossings = np.clip(crossings, -1.0, 1.0)
        return pd.Series(crossings, index=frame.index, dtype=float)
