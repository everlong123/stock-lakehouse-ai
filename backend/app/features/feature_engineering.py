"""Gold-layer feature engineering orchestrator."""

from __future__ import annotations

import pandas as pd

from app.core.exceptions import DataValidationError
from app.features.advanced_features import (
    add_advanced_indicators,
    add_candlestick_features,
    add_volume_profile_features,
    add_composite_signals,
)
from app.features.macro_features import MacroFeatureBuilder, add_market_regime_features
from app.features.price_features import add_price_features
from app.features.target_features import add_target_features
from app.features.technical_features import add_technical_features

# Columns that are *not* derived features - everything else is considered a
# prior derived feature and is dropped before we re-derive them.  This makes
# build_gold_features idempotent and tolerant of contaminated Silver inputs
# (e.g. parquet files that already contain prior Gold features).
_BASE_INPUT_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "source",
    "ingestion_time",
    "year",
    "month",
)


def build_gold_features(frame: pd.DataFrame, include_macro: bool = True) -> pd.DataFrame:
    """
    Build Gold features per symbol, sorted by timestamp, with no future leakage.

    Args:
        frame: DataFrame with OHLCV columns
        include_macro: Whether to include macro features (slower but more context for ML)

    Returns:
        DataFrame with all features
    """
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise DataValidationError(f"Feature engineering missing columns: {sorted(missing)}")

    # Strip any pre-existing derived columns so the pipeline is idempotent.
    keep = [c for c in _BASE_INPUT_COLUMNS if c in frame.columns]
    working_input = frame.loc[:, keep].copy()

    parts: list[pd.DataFrame] = []
    macro_builder = MacroFeatureBuilder() if include_macro else None

    for symbol, group in working_input.groupby("symbol", sort=True):
        ordered = group.sort_values("timestamp").copy().reset_index(drop=True)

        # Core features (basic technical indicators)
        ordered = add_technical_features(ordered)
        ordered = add_price_features(ordered)
        ordered = add_target_features(ordered)

        # Advanced indicators (momentum, volatility, trend strength)
        ordered = add_advanced_indicators(ordered)

        # Candlestick patterns
        ordered = add_candlestick_features(ordered)

        # Volume profile features
        ordered = add_volume_profile_features(ordered)

        # Composite signals
        ordered = add_composite_signals(ordered)

        # Market regime features
        ordered = add_market_regime_features(ordered)

        # Macro features (optional - adds context but slower)
        if macro_builder is not None and len(ordered) > 50:
            try:
                ordered = macro_builder.build(ordered)
            except Exception:
                pass  # Skip macro if provider fails

        ordered["symbol"] = symbol
        parts.append(ordered)

    result = pd.concat(parts, ignore_index=True)
    return result.loc[:, ~result.columns.duplicated()]


def build_gold_features_simple(frame: pd.DataFrame) -> pd.DataFrame:
    """Build Gold features without macro features (faster for simple use cases)."""
    return build_gold_features(frame, include_macro=False)


def drop_warmup_rows(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    """Drop rows with NaN features. Target NaNs on the last row are expected."""
    return frame.dropna(subset=feature_columns).reset_index(drop=True)
