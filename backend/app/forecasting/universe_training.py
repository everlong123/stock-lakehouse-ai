"""Universe-wide model training.

WHY THIS FILE EXISTS
--------------------
Until now, only 18 symbols had a trained model on disk, because training
was something a person did by hand for a handful of tickers. That made
the system's reach a curated list rather than the whole lakehouse, and it
made the "next-session forecast" a demo instead of a system.

This module trains a model for EVERY symbol that has usable Gold history.

THE MEASURED COST THAT MADE THIS FEASIBLE
-----------------------------------------
Measured on this machine on 13/11/2026 (see
``scripts/_probe_forecast_cost.py``), with the lakehouse holding ~897
symbols in Gold:

    Gold read (MinIO) .............. 0.41 s median
    train linear_regression ......... 0.45 s median
    train arima ..................... 7.81 s median
    train lstm ...................... 7.04 s median

So the LINEAR REGRESSION model costs ~0.9 s per symbol end to end, which
is ~13 minutes for the whole universe - a nightly job, not a weekend.
ARIMA at 7.8 s per symbol would be ~2 hours, and LSTM's torch import
makes it unsuitable for a batch on a small VPS. That is why the universe
model is LINEAR REGRESSION: it is the only model whose cost is compatible
with "every symbol, every night".

THE MODEL IS STILL A REAL MODEL
-------------------------------
This is ordinary least squares over 21 Gold features (price, volume,
moving averages, RSI, MACD, Bollinger bands, lagged returns), fitted on a
chronological split with the same trainer the API uses. It is not a
moving average and not a constant. The academic point of the thesis -
comparing three model families on the same hold-out split - is untouched,
because the ARIMA and LSTM models are still trained for the symbols where
they are worth their cost.

WHY TRAINING IS SEPARATE FROM FORECASTING
-----------------------------------------
Training writes a model; forecasting reads one. Keeping them apart lets
the nightly batch re-use models that are days old without paying the
training cost again, and it lets a training pass be re-run without
disturbing the forecasts that are already published.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from app.core.logging_config import get_logger
from app.forecasting.trainer import train_model
from app.lakehouse import frame_cache
from app.lakehouse.gold import GoldLayer

logger = get_logger(__name__)

#: How many symbols' Gold frames are read at the same time. See the
#: module docstring in `app/lakehouse/frame_cache.py` for why the reads
#: overlap and why the number is not higher.
_READ_WORKERS = int(os.getenv("UNIVERSE_READ_WORKERS", "8"))

#: The model used for the universe-wide pass. See the module docstring for
#: the measured cost that decided this.
UNIVERSE_MODEL = "linear_regression"

#: A symbol needs at least this many Gold rows before a model is worth
#: training: the chronological split carves 60/20/20 out of the rows, and
#: the indicator warm-up (the longest rolling window is 50 sessions) eats
#: the first ~50 rows anyway.
MIN_TRAINING_ROWS = 300


@dataclass
class TrainingSummary:
    """What one training pass did."""

    trained: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "trained": len(self.trained),
            "skipped": len(self.skipped),
            "failed": len(self.failed),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "failed_detail": self.failed,
        }


def list_gold_symbols() -> list[str]:
    """Every symbol that has data in the Gold layer.

    The listing is done on the storage backend directly rather than by
    reading each symbol, because reading 897 symbols just to learn their
    names would cost ~6 minutes of MinIO round-trips.
    """
    layer = GoldLayer()
    symbols: list[str] = []
    for key in layer.storage.list_objects("gold"):
        marker = "symbol="
        if marker not in key:
            continue
        tail = key.split(marker, 1)[1]
        symbol = tail.split("/", 1)[0]
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return sorted(symbols)


def train_universe(
    symbols: Iterable[str] | None = None,
    model_name: str = UNIVERSE_MODEL,
    force: bool = False,
    progress: Callable[[int, int, str], None] | None = None,
    end_date: Any | None = None,
    full_fit: bool = False,
) -> TrainingSummary:
    """Train ``model_name`` for every symbol that needs it.

    ``force=False`` skips a symbol that already has a trained model, so a
    nightly re-run costs nothing for the symbols that have not changed.
    A model is considered stale when the symbol's newest Gold session is
    NEWER than the model's training end - that is the case where the
    model has not seen the latest sessions and its forecast would be
    anchored on a stale price.

    ``end_date`` truncates every symbol's history to that boundary before
    the chronological split is carved out. This is the *rolling refit*
    mode: the model only ever sees sessions up to ``end_date``, so the
    hold-out it is scored on is genuinely unseen data. Combined with
    ``--end-date`` on the command line, it makes the nightly job a
    walk-forward evaluation instead of a single retrospective fit.

    ``full_fit`` ships the model fitted on 100% of the (truncated)
    history while still reporting the hold-out metrics from the same
    60/20/20 split. See ``train_model`` for why the metric is computed
    the same way in both modes.
    """
    from app.forecasting.model_registry import load_registry_record, model_directory

    summary = TrainingSummary()
    started = time.perf_counter()

    target = list(symbols) if symbols is not None else list_gold_symbols()
    layer = GoldLayer()

    # A rolling refit always trains: the point is to produce a model whose
    # training window ends at `end_date`, so the freshness probe (which
    # compares against the newest stored session) does not apply.
    rolling = end_date is not None

    # The freshness probe needs the symbol's newest Gold session, and the
    # training itself needs the whole frame. Both come from the same
    # read, so the frames are warmed CONCURRENTLY first: a read costs
    # ~0.5 s (measured 13/11/2026) and the pass covers ~950 symbols.
    #
    # Only the symbols that actually need training are read - a symbol
    # with a fresh model is skipped without any storage access at all.
    stale: list[str] = []
    for symbol in target:
        symbol = symbol.upper()
        if rolling:
            stale.append(symbol)
            continue
        try:
            if not force and _has_fresh_model(symbol, model_name, layer, load_registry_record, model_directory):
                summary.skipped[symbol] = "already trained"
                continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("Freshness probe failed for %s: %s", symbol, exc)
        stale.append(symbol)

    if stale:
        frame_cache.warm_cache("gold", stale, reader=layer.read, workers=_READ_WORKERS)

    for index, symbol in enumerate(stale, start=1):
        try:
            frame = layer.read(symbol)
            if len(frame) < MIN_TRAINING_ROWS:
                summary.skipped[symbol] = f"only {len(frame)} rows in Gold"
                continue

            train_model(
                symbol,
                model_name,
                extra_params={"epochs": 8},
                end_date=end_date,
                full_fit=full_fit,
            )
            summary.trained.append(symbol)
            if progress:
                progress(index, len(stale), symbol)
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the pass
            logger.warning("Universe training failed for %s: %s", symbol, exc)
            summary.failed[symbol] = str(exc)

    summary.elapsed_seconds = time.perf_counter() - started
    logger.info(
        "Universe training: %d trained, %d skipped, %d failed in %.1fs",
        len(summary.trained),
        len(summary.skipped),
        len(summary.failed),
        summary.elapsed_seconds,
    )
    return summary


def _has_fresh_model(
    symbol: str,
    model_name: str,
    layer: GoldLayer,
    load_registry_record: Any,
    model_directory: Any,
) -> bool:
    """True when the symbol already has a model trained on its latest data.

    A model is FRESH when its training end reaches the symbol's newest
    stored session. A model that stopped short of the newest session is
    stale: the forecast it produces would be anchored on a price that is
    no longer the last close.
    """
    try:
        directory = model_directory(symbol, model_name)
        if not (directory / "registry.json").exists():
            return False
        registry = load_registry_record(symbol, model_name)
    except Exception:  # noqa: BLE001
        return False

    train_end = registry.get("train_end")
    if not train_end:
        return False

    try:
        import pandas as pd

        trained_through = pd.to_datetime(train_end, utc=True)
    except Exception:  # noqa: BLE001
        return False

    try:
        newest = layer.latest_timestamp(symbol)
    except Exception:  # noqa: BLE001
        return False
    if newest is None:
        return False

    # The model has seen everything if its training window reaches the
    # newest stored session. A model trained on a chronological split
    # never reaches the newest session by construction (the split holds
    # the last 20% out), so the check is against the HOLD-OUT boundary:
    # the model is fresh when the hold-out covers the newest session, i.e.
    # the newest session is inside the scored range.
    test_end = registry.get("test_end")
    if test_end:
        try:
            return pd.to_datetime(test_end, utc=True) >= newest
        except Exception:  # noqa: BLE001
            pass
    return False
