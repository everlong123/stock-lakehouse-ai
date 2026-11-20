"""Refuse to train a model on a history that mixes price scales.

WHY THIS FILE EXISTS
--------------------
A reverse split changes a symbol's price scale, and the lakehouse stores
both the pre-split and the post-split prices. The rows are all real - every
one is a price the exchange printed - but a price-LEVEL model fitted across
the break learns nothing, and its extrapolation can land below zero.

The measured case (18/11/2026): ``SOXS`` produced a forecast of
-277.289.577 against a reference close of 58,77. The write path refused to
store it, so no negative price reached the ledger, but the MODEL was still
trained and still sat in the registry.

So the training path now asks whether the history sits on one scale.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.core.exceptions import ModelTrainingError
from app.forecasting import trainer


def _history(closes: list[float], start: str = "2020-01-01") -> pd.DataFrame:
    """A frame with one row per close, on consecutive sessions."""
    stamps = pd.date_range(start=start, periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "close": closes,
            "volume": [1_000_000] * len(closes),
            "symbol": ["TEST"] * len(closes),
        }
    )


def test_a_history_on_one_scale_is_accepted() -> None:
    """A healthy symbol trains normally."""
    frame = _history([100.0 + i * 0.1 for i in range(120)])
    trainer._reject_contaminated_history("TEST", frame)


def test_a_history_with_a_reverse_split_is_rejected() -> None:
    """The measured failure: a big scale break stops the training."""
    closes = [191_160_000.0] * 60 + [58.77] * 60
    frame = _history(closes)
    with pytest.raises(ModelTrainingError) as excinfo:
        trainer._reject_contaminated_history("SOXS", frame)
    message = str(excinfo.value)
    assert "SOXS" in message
    assert "scale" in message.lower()


def test_the_rejection_names_the_span_and_the_reason() -> None:
    """The message must say WHY and HOW BIG, so the operator can act."""
    closes = [191_160_000.0] * 60 + [58.77] * 60
    frame = _history(closes)
    with pytest.raises(ModelTrainingError) as excinfo:
        trainer._reject_contaminated_history("SOXS", frame)
    message = str(excinfo.value)
    assert "span" in message.lower()
    assert "reverse split" in message.lower()
    assert "re-ingest" in message.lower()


def test_a_symbol_that_only_grows_is_not_rejected() -> None:
    """Growth is not a scale break: NVDA's 30x span must stay trainable.

    The span threshold is 100x for a measured reason - at 20x it would flag
    NVDA and CELH, two healthy symbols that simply grew, and a false
    accusation is as bad as a missed one.
    """
    frame = _history([10.0 * (1.05**i) for i in range(120)])
    trainer._reject_contaminated_history("NVDA", frame)


def test_an_empty_frame_is_not_rejected() -> None:
    """An empty frame is handled by the caller, not by this check."""
    frame = pd.DataFrame({"timestamp": [], "close": []})
    trainer._reject_contaminated_history("EMPTY", frame)
