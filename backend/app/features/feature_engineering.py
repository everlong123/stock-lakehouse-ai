"""Gold-layer feature engineering orchestrator."""

from __future__ import annotations

import pandas as pd

from app.core.exceptions import DataValidationError
from app.features.price_features import add_price_features
from app.features.target_features import add_target_features
from app.features.technical_features import add_technical_features


def build_gold_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Build Gold features per symbol, sorted by timestamp, with no future leakage."""
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise DataValidationError(f"Feature engineering missing columns: {sorted(missing)}")

    parts: list[pd.DataFrame] = []
    for symbol, group in frame.groupby("symbol", sort=True):
        ordered = group.sort_values("timestamp").copy().reset_index(drop=True)
        ordered = add_technical_features(ordered)
        ordered = add_price_features(ordered)
        ordered = add_target_features(ordered)
        ordered["symbol"] = symbol
        parts.append(ordered)
    result = pd.concat(parts, ignore_index=True)
    return result.loc[:, ~result.columns.duplicated()]


def drop_warmup_rows(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    """Drop rows with NaN features. Target NaNs on the last row are expected."""
    return frame.dropna(subset=feature_columns).reset_index(drop=True)
