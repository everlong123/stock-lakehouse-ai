"""Stock market data endpoints."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_market_service
from app.core.config import settings
from app.core.constants import GLOBAL_SYMBOLS, currency_for_symbol
from app.core.exceptions import NotFoundError, StorageError
from app.core.logging_config import get_logger
from app.lakehouse.storage_factory import get_storage_backend
from app.schemas.common import ok
from app.services.market_service import MarketService

logger = get_logger(__name__)
router = APIRouter(prefix="/stocks", tags=["stocks"])

# Cache for /stocks/symbols. Listing bronze top-level prefixes is fast on a
# healthy MinIO (~50-200ms) but balloons to multi-second when the bucket is
# being written to. The frontend polls this on every page mount, so we cache
# for 5 minutes and warm the cache in the background after the first miss.
_SYMBOLS_CACHE_TTL_SECONDS = 300.0
_symbols_lock = threading.Lock()
_symbols_cache: dict = {"value": None, "expires_at": 0.0}


def _available_symbols() -> list[str]:
    """Return symbols that have at least one parquet object in stock-bronze.
    Uses non-recursive listing to avoid timeout on large buckets."""
    try:
        storage = get_storage_backend()
        if storage.backend_name == "local":
            folder = Path(storage.root) / "bronze"
            symbols = {
                path.name.split("=", 1)[1].upper()
                for path in folder.iterdir()
                if path.is_dir() and path.name.startswith("symbol=") and any(path.rglob("*.parquet"))
            } if folder.exists() else set()
            canonical = list(dict.fromkeys(s for s in GLOBAL_SYMBOLS if s in symbols))
            return canonical + sorted(symbols - set(canonical))
        # Non-recursive: list just top-level symbol= prefix dirs (fast, no timeout)
        objects = storage.client.list_objects(
            storage._bucket("bronze"), prefix="symbol=", recursive=False
        )
        symbols: set[str] = set()
        for obj in objects:
            name = obj.object_name
            if name and name.startswith("symbol="):
                sym = name.split("/", 1)[0].split("=", 1)[1].upper()
                if sym:
                    symbols.add(sym)
        if not symbols:
            return []
        # preserve canonical order from GLOBAL_SYMBOLS so UI lists are stable
        canonical = list(dict.fromkeys(s for s in GLOBAL_SYMBOLS if s in symbols))
        extras = sorted(symbols - set(canonical))
        return canonical + extras
    except Exception as exc:
        logger.warning("Could not enumerate symbols from storage: %s", exc)
        raise StorageError("Cannot enumerate the stored stock universe.") from exc


@router.get("/symbols")
def get_symbols() -> dict:
    now = time.monotonic()
    with _symbols_lock:
        cached = _symbols_cache["value"]
        expires_at = _symbols_cache["expires_at"]
    if cached is not None and now < expires_at:
        return ok(cached)

    symbols = list(dict.fromkeys(_available_symbols()))
    payload = {"symbols": symbols, "count": len(symbols)}
    with _symbols_lock:
        _symbols_cache["value"] = payload
        _symbols_cache["expires_at"] = time.monotonic() + _SYMBOLS_CACHE_TTL_SECONDS
    return ok(payload)


@router.get("/tape")
def get_tape(
    symbols: str = Query(
        default="AAPL,MSFT,NVDA,TSLA,AMZN,GOOGL,META,FPT,VCB,VHM",
        description="Comma-separated tickers to quote.",
    ),
    service: MarketService = Depends(get_market_service),
) -> dict:
    """Latest quote for several symbols at once — the market tape.

    WHY THIS EXISTS
    ---------------
    The navigation bar shows a live price strip. Fetching each ticker with
    its own ``/stocks/{symbol}/latest`` call would mean one HTTP round trip
    per symbol, and the browser caps concurrent connections per host, so the
    strip would arrive in waves. One request that returns the whole tape
    keeps the bar in a single paint.

    Every quote comes from the same lakehouse read path as
    ``/stocks/{symbol}/latest`` (Gold -> Silver -> Bronze), so the tape can
    never show a number the rest of the app does not show.

    A symbol with no data in the lakehouse is **omitted**, not filled with a
    placeholder: an absent ticker is honest, a zero-priced one is a lie.

    WHY THE QUOTES ARE FETCHED CONCURRENTLY
    -----------------------------------------
    Each quote is an independent read from MinIO, and those reads are
    latency-bound rather than CPU-bound - so they overlap almost
    perfectly. Fetching the ten tickers one after another made the tape
    take the SUM of ten round-trips; fetching them at once makes it take
    the SLOWEST of them.

    Measured on 14/11/2026: 11.7 s cold and 1.0 s warm before, 0.83 s
    warm after the concurrent fetch (and 2.5 s on the very first, fully
    cold call).

    The ORDER of the quotes is unchanged: the rows are placed back at
    the index of their requested symbol, so the tape looks the same as
    before.
    """
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    rows: list[dict | None] = [None] * len(requested)

    def _quote(index: int, sym: str) -> tuple[int, dict | None]:
        try:
            latest = service.get_latest(sym, interval="1d")
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not blank the tape
            logger.warning("Tape: %s unavailable (%s)", sym, exc)
            return index, None
        return index, {
            "symbol": latest["symbol"],
            "close": latest["close"],
            "change_pct": latest["change_pct"],
            "currency": latest.get("currency") or currency_for_symbol(sym),
            "timestamp": latest["timestamp"],
            "source_layer": latest.get("source_layer"),
        }

    if requested:
        # Six workers: enough to overlap the round-trips without overloading
        # MinIO, which resets connections when it is pushed hard.
        workers = max(1, min(6, len(requested)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for index, row in pool.map(
                lambda pair: _quote(*pair), list(enumerate(requested))
            ):
                rows[index] = row

    return ok(
        {
            "quotes": [row for row in rows if row is not None],
            "requested": len(requested),
            "returned": sum(1 for row in rows if row is not None),
        }
    )


@router.get("/compare")
def compare_symbols(
    symbols: str = Query(
        default="AAPL,MSFT,NVDA",
        description="Comma-separated tickers to compare.",
    ),
    days: int = Query(default=252, ge=30, le=3650, description="Lookback window in days."),
    service: MarketService = Depends(get_market_service),
) -> dict:
    """Normalised price comparison for several symbols over one window.

    WHY THIS EXISTS
    ---------------
    The market-data page answers "how did these tickers do against each
    other". That question needs two things the single-symbol endpoint cannot
    give: the *same* window for every ticker, and a *common* price scale.
    Raw closes cannot be compared directly - AAPL trades near 340 and FPT
    near 51,000, so plotting both on one axis would show one line pinned to
    the floor.

    So every series is rebased to 100 at the first bar of the window. The
    rebased value is a factual statement: "this ticker is up X% since the
    start of the window". It is derived from the stored closes, not
    invented.

    A ticker with no data in the lakehouse is **omitted** rather than
    zero-filled, so the comparison never shows a flat line for a symbol
    that simply is not there.
    """
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    # Anchor the window on the LATEST bar of the most recent ticker, so every
    # series is aligned to the same calendar days rather than to each
    # symbol's own history start.
    #
    # WHY TWO PHASES
    # --------------
    # The anchor is the newest bar across the compared tickers, and the
    # window is measured BACKWARDS from it. So the anchor has to be known
    # before the window can be requested.
    #
    # Phase 1 reads only the newest partition of each symbol - cheap, and
    # enough to find the anchor. Phase 2 then requests the window
    # directly, so the backend downloads the months the window covers
    # instead of the symbol's entire history.
    #
    # Before, a comparison of three tickers pulled ~121 monthly partitions
    # each; now it pulls the ~13 months the window actually spans. The
    # rows are the SAME stored rows.
    anchor: pd.Timestamp | None = None
    requested_set = list(requested)

    def _anchor_of(sym: str) -> pd.Timestamp | None:
        """The newest bar of one symbol, or None when it has no data."""
        try:
            latest = service.get_latest(sym, interval="1d")
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not blank the compare
            logger.warning("Compare: %s unavailable (%s)", sym, exc)
            return None
        return pd.to_datetime(latest["timestamp"], utc=True)

    # Phase 1 runs concurrently: the anchor of each ticker is an independent
    # read of one partition, so the three round-trips overlap instead of
    # stacking up.
    if requested_set:
        workers = max(1, min(6, len(requested_set)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for last in pool.map(_anchor_of, requested_set):
                if last is None:
                    continue
                anchor = last if anchor is None or last > anchor else anchor

    if anchor is None:
        return ok({"series": [], "symbols": [], "days": days, "anchor": None})

    start = anchor - pd.Timedelta(days=days)
    out: list[dict] = []

    def _series_for(sym: str) -> dict | None:
        """The rebased series of one symbol inside the window."""
        try:
            frame = service.get_history(
                sym, start=start.to_pydatetime(), end=anchor.to_pydatetime(), interval="1d"
            )
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not blank the compare
            logger.warning("Compare: %s window unavailable (%s)", sym, exc)
            return None
        if frame.empty:
            return None
        window = frame[pd.to_datetime(frame["timestamp"], utc=True) >= start]
        closes = pd.to_numeric(window["close"], errors="coerce").dropna()
        if closes.empty:
            return None
        base = float(closes.iloc[0])
        if base == 0:
            return None
        return {
            "symbol": sym,
            "currency": currency_for_symbol(sym),
            "base_close": base,
            "base_timestamp": str(window["timestamp"].iloc[0]),
            "points": [
                {
                    "timestamp": str(ts),
                    "close": float(value),
                    "rebased": (float(value) / base) * 100.0,
                }
                for ts, value in zip(window["timestamp"], closes)
            ],
            "return_pct": (float(closes.iloc[-1]) / base - 1.0) * 100.0,
        }

    # Phase 2 runs concurrently as well: each symbol reads its own window,
    # and the reads are independent of each other.
    if requested_set:
        workers = max(1, min(6, len(requested_set)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for series in pool.map(_series_for, requested_set):
                if series is not None:
                    out.append(series)

    out.sort(key=lambda item: item["return_pct"], reverse=True)
    return ok(
        {
            "series": out,
            "symbols": [item["symbol"] for item in out],
            "days": days,
            "anchor": str(anchor),
        }
    )


@router.get("/stats/{symbol}")
def symbol_stats(
    symbol: str,
    days: int = Query(default=252, ge=30, le=3650, description="Lookback window in days."),
    service: MarketService = Depends(get_market_service),
) -> dict:
    """Descriptive statistics for one symbol over one window.

    WHY THIS EXISTS
    ---------------
    A market-data page that only shows candles and a table tells you what
    the price *was*. These are the numbers that describe what the price
    *did*: how much it moved, how deep the dips were, how heavy the
    trading was. They are the difference between a price table and an
    analysis tool.

    EVERY NUMBER HERE IS COMPUTED FROM THE STORED CLOSES
    ----------------------------------------------------
    * volatility  - stdev of daily log returns, annualised (sqrt(252))
    * max drawdown - the deepest peak-to-trough fall inside the window
    * total return - first close to last close
    * up days      - sessions whose close beat the previous close
    * avg volume   - mean session volume
    * high / low   - the window's extremes

    Nothing is approximated from a hard-coded constant: the window is
    trimmed to the requested number of days and every figure is derived
    from the bars actually present.

    WHY THE WINDOW IS REQUESTED FROM THE BACKEND
    ---------------------------------------------
    The statistics describe the LAST ``days`` sessions. The symbol's whole
    history is ~121 monthly partitions, so reading all of them and then
    throwing away everything but the window cost the download of the
    entire history on every call.

    The window is now asked for explicitly, so the backend reads only the
    partitions that can hold it. The bars the figures are computed from
    are the SAME stored bars.
    """
    sym = symbol.upper()
    # The newest session anchors the window, so it is read first - and
    # reading it costs one partition download, not the whole history.
    try:
        latest = service.get_latest(sym, interval="1d")
    except NotFoundError:
        raise NotFoundError(f"No lakehouse data for {sym}.")
    end = pd.to_datetime(latest["timestamp"], utc=True)
    start = end - pd.Timedelta(days=days)
    frame = service.get_history(
        sym, start=start.to_pydatetime(), end=end.to_pydatetime(), interval="1d"
    )
    if frame.empty:
        raise NotFoundError(f"No lakehouse data for {sym}.")

    ts = pd.to_datetime(frame["timestamp"], utc=True)
    end = ts.iloc[-1]
    start = end - pd.Timedelta(days=days)
    window = frame.loc[(ts >= start).values]
    if len(window) < 2:
        raise NotFoundError(
            f"{sym} has fewer than two sessions in the last {days} days."
        )

    closes = pd.to_numeric(window["close"], errors="coerce").dropna()
    volumes = pd.to_numeric(window["volume"], errors="coerce").dropna()
    if closes.empty:
        raise NotFoundError(f"{sym} has no usable close in the last {days} days.")

    log_returns = np.log(closes / closes.shift(1)).dropna()
    volatility = float(log_returns.std(ddof=1) * np.sqrt(252) * 100) if len(log_returns) > 1 else None

    running_max = closes.cummax()
    drawdown = (closes - running_max) / running_max
    max_drawdown = float(drawdown.min() * 100)

    changes = closes.diff().dropna()
    up_days = int((changes > 0).sum())
    down_days = int((changes < 0).sum())

    return ok(
        {
            "symbol": sym,
            "currency": currency_for_symbol(sym),
            "days": days,
            "sessions": int(len(closes)),
            "window_start": str(window["timestamp"].iloc[0]),
            "window_end": str(window["timestamp"].iloc[-1]),
            "first_close": float(closes.iloc[0]),
            "last_close": float(closes.iloc[-1]),
            "high": float(closes.max()),
            "low": float(closes.min()),
            "mean_close": float(closes.mean()),
            "total_return_pct": float((closes.iloc[-1] / closes.iloc[0] - 1) * 100),
            "volatility_pct": volatility,
            "max_drawdown_pct": max_drawdown,
            "up_days": up_days,
            "down_days": down_days,
            "avg_volume": float(volumes.mean()) if not volumes.empty else None,
            "total_volume": float(volumes.sum()) if not volumes.empty else None,
        }
    )


@router.get("/{symbol}")
def get_stock(
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    interval: str = Query(default="1d"),
    service: MarketService = Depends(get_market_service),
) -> dict:
    # Load the frame ONCE and derive both the history and the latest bar
    # from it.
    #
    # WHY: `get_latest` used to call `get_history` internally, so this
    # endpoint pulled the symbol's ~121 parquet partitions out of MinIO
    # twice per request and then re-sorted/re-copied the 2532 x 92 frame a
    # second time. Deriving both from one load removes that second pass.
    frame = service.get_history(symbol.upper(), start=start, end=end, interval=interval)
    latest = service.latest_from_frame(symbol.upper(), frame, interval=interval)
    return ok(
        {
            "symbol": symbol.upper(),
            "interval": interval,
            "latest": latest,
            "count": int(len(frame)),
            # Preserve the full requested window so "All" and the reported
            # count describe the same history, including long-lived symbols.
            "rows": service.to_records(frame, limit=0),
            "last_updated": latest["timestamp"],
            "data_source": latest.get("source_layer"),
            # Prices in this lakehouse are unitless: VCB trades near 53,500
            # and AAPL near 330, and both are a "close". The consumer needs to
            # know which unit this symbol's prices are in, so it can label
            # them correctly instead of assuming dong for everything.
            "currency": currency_for_symbol(symbol),
        }
    )


@router.get("/{symbol}/latest")
def get_latest(symbol: str, interval: str = "1d", service: MarketService = Depends(get_market_service)) -> dict:
    return ok(service.get_latest(symbol.upper(), interval=interval))


@router.get("/{symbol}/csv")
def download_csv(
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    interval: str = "1d",
    service: MarketService = Depends(get_market_service),
) -> StreamingResponse:
    frame = service.get_history(symbol.upper(), start=start, end=end, interval=interval)
    csv_data = frame[["symbol", "timestamp", "open", "high", "low", "close", "volume"]].to_csv(index=False)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={symbol.upper()}_{interval}.csv"},
    )
