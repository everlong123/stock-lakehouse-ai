"""Indicator computation service used by APIs and the Gold layer."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.indicators.bollinger import bollinger_bands
from app.indicators.ema import ema
from app.indicators.macd import macd
from app.indicators.rsi import rsi
from app.indicators.sma import sma


def _scalar(value) -> float | None:
    if isinstance(value, pd.Series):
        value = value.iloc[-1] if len(value) else None
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


@dataclass
class IndicatorConfig:
    """User-configurable indicator parameters."""

    sma_windows: tuple[int, ...] = (5, 10, 20, 50)
    ema_windows: tuple[int, ...] = (12, 26)
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_window: int = 20
    bb_std: float = 2.0


RESERVED_COLUMNS = {
    # Indicator columns produced by this module.  Drop them on the input
    # so the function is idempotent and safe to call on contaminated frames
    # (e.g. Silver parquet files that already contain prior Gold features).
    "sma_5", "sma_10", "sma_20", "sma_50",
    "ema_12", "ema_26",
    "rsi_14",
    "macd", "macd_signal", "macd_hist",
    "bb_middle", "bb_upper", "bb_lower",
}


def add_indicators(frame: pd.DataFrame, config: IndicatorConfig | None = None) -> pd.DataFrame:
    """Attach SMA, EMA, RSI, MACD, and Bollinger columns to an OHLCV frame."""
    if "close" not in frame.columns:
        raise ValueError("Indicator calculation requires a close column.")
    config = config or IndicatorConfig()
    # Drop any pre-existing indicator columns so the function is idempotent.
    result = frame.drop(columns=[c for c in RESERVED_COLUMNS if c in frame.columns]).copy()
    close = result["close"]
    for window in config.sma_windows:
        result[f"sma_{window}"] = sma(close, window)
    for window in config.ema_windows:
        result[f"ema_{window}"] = ema(close, window)
    result["rsi_14"] = rsi(close, config.rsi_period)
    macd_frame = macd(close, config.macd_fast, config.macd_slow, config.macd_signal)
    result = pd.concat([result, macd_frame], axis=1)
    bands = bollinger_bands(close, config.bb_window, config.bb_std)
    result = pd.concat([result, bands], axis=1)
    return result


# ── Indicator summary ─────────────────────────────────────────────────────
#
# WHY THE SUMMARY IS A SET OF FACTS AND NOT A PARAGRAPH
# ----------------------------------------------------
# The frontend renders this summary in the reader's language (Vietnamese or
# English), and the same sentence has to be translated into both. If the
# backend wrote the prose, the English text would be baked in and the
# Vietnamese UI would show an English paragraph — which is what happened
# before this change.
#
# So the backend reports the FACTS it observed, as stable machine-readable
# keys plus the numbers they refer to, and the frontend turns them into a
# sentence in the active locale. The numbers are still computed here, from
# the same real snapshot, so nothing about the measurement moves to the
# client.
#
# The keys are part of the API contract: `describe_indicators` returns
# `{"trend": {"code": ..., "width": ...}, ...}`.


def describe_indicators(latest: pd.Series) -> dict[str, dict]:
    """Return the descriptive (non-advisory) facts about the latest snapshot.

    Each of the three groups ("trend", "momentum", "volatility") carries a
    ``code`` naming the observation and the numbers it rests on. The code
    set is closed:

    trend:     ``uptrend`` | ``downtrend`` | ``mixed`` | ``insufficient``
    momentum:  ``rsi_elevated`` | ``rsi_depressed`` | ``rsi_mid`` | ``insufficient``
    volatility:``bb_above`` | ``bb_below`` | ``bb_inside`` | ``insufficient``
    """
    insufficient = {"code": "insufficient"}
    close = _scalar(latest.get("close"))
    sma20 = _scalar(latest.get("sma_20"))
    sma50 = _scalar(latest.get("sma_50"))
    rsi_value = _scalar(latest.get("rsi_14"))
    bb_upper = _scalar(latest.get("bb_upper"))
    bb_lower = _scalar(latest.get("bb_lower"))

    trend: dict[str, object] = dict(insufficient)
    if close is not None and sma20 is not None and sma50 is not None:
        if close > sma20 > sma50:
            trend = {"code": "uptrend"}
        elif close < sma20 < sma50:
            trend = {"code": "downtrend"}
        else:
            trend = {"code": "mixed"}

    momentum: dict[str, object] = dict(insufficient)
    if rsi_value is not None:
        if rsi_value >= 70:
            momentum = {"code": "rsi_elevated", "rsi": round(rsi_value, 2)}
        elif rsi_value <= 30:
            momentum = {"code": "rsi_depressed", "rsi": round(rsi_value, 2)}
        else:
            momentum = {"code": "rsi_mid", "rsi": round(rsi_value, 2)}

    volatility: dict[str, object] = dict(insufficient)
    if close is not None and bb_upper is not None and bb_lower is not None:
        width = bb_upper - bb_lower
        if close > bb_upper:
            volatility = {"code": "bb_above", "width": round(width, 2)}
        elif close < bb_lower:
            volatility = {"code": "bb_below", "width": round(width, 2)}
        else:
            volatility = {"code": "bb_inside", "width": round(width, 2)}

    return {"trend": trend, "momentum": momentum, "volatility": volatility}
