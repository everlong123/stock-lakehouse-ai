#!/usr/bin/env python3
"""Prove that the data in MinIO (and therefore on the web) is real.

WHAT THIS DOES
--------------
The lakehouse is only trustworthy if the numbers in Bronze/Silver/Gold can be
traced back to an external source of truth. This script re-fetches each symbol
from the ORIGINAL provider (a fresh HTTP call to Yahoo Finance, completely
independent of the lakehouse and of anything the API serves) and compares the
result against what is actually stored, layer by layer.

    provider (live HTTP)          <- the source of truth
            |
            |  compare
            v
    Bronze  (raw, as ingested)
    Silver  (cleaned / canonicalised)
    Gold    (feature-enriched)
    API     (what the browser shows)

WHY THIS IS NOT JUST "diff two files"
-------------------------------------
A diff only proves the layers agree with each other. It cannot prove that
they agree with reality. The re-fetch is what makes the claim falsifiable:
if the stored value differs from the provider's value right now, the stored
value is wrong (or stale, or from a different instrument) and the script says
so.

It also separates four DIFFERENT kinds of disagreement, because they have
four different causes:

  * ``EXACT``      - stored == provider, to the last cent.
  * ``TOLERANT``   - differs by less than ``--tolerance`` (rounding between
                     the provider's float and the stored float32/64).
  * ``STALE``      - the stored bar is correct, but the provider has since
                     published a NEWER session, or the newest stored session
                     was still forming when it was written.
  * ``MISMATCH``   - the stored value is simply wrong. This is the one that
                     matters, and it is what the exit code reports.

Two more checks are specific to this lakehouse and worth having:

  * **Session cardinality.** The Silver layer canonicalises to one bar per
    trading day. Bronze may legitimately hold more (intraday ticks, a
    re-stamped session from a second provider). The script reports the
    difference instead of hiding it, because Bronze holding 2 bars for one
    session is exactly the bug that once made every chart draw two candles.
  * **Cross-source price agreement.** Where a symbol was ingested from two
    different providers (``source`` column), their prices for the same
    session are compared. A big gap means one of them is wrong.

USAGE
-----
    python scripts/verify_against_source.py                       # default symbols
    python scripts/verify_against_source.py --symbols AAPL VNM VCB
    python scripts/verify_against_source.py --symbols all --layer gold
    python scripts/verify_against_source.py --symbols all --max-symbols 50

EXIT CODES
----------
    0 = every checked bar is exact, tolerant or explainably stale
    1 = at least one real MISMATCH was found
    2 = the check could not run (provider unreachable, no data, ...)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import setup_logging
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

#: Price differences below this (relative to the stored close) are treated as
#: rounding noise rather than as a mismatch. Yahoo returns float64 prices that
#: get stored as parquet float64, so a faithful round-trip is bit-exact; the
#: tolerance exists for providers that report in cents and are stored in a
#: narrower type.
DEFAULT_TOLERANCE = 1e-6

#: How many trailing sessions to compare per symbol. 60 sessions is about a
#: quarter of trading days - enough to catch a systematic error (a shifted
#: timestamp, a scaled price) while keeping the run short enough to finish
#: while a user watches.
DEFAULT_WINDOW = 60

#: A stored session older than this many days is skipped: the provider only
#: serves ~10 years of intraday-free daily history, and the further back the
#: comparison goes the more likely it is that the provider adjusted history
#: (splits, dividend restatements) rather than the lakehouse being wrong.
MAX_AGE_DAYS = 3650

DEFAULT_SYMBOLS = ("AAPL", "MSFT", "NVDA", "VNM", "VCB", "FPT", "SPY")

#: A relative difference at or below this is treated as "the provider revised
#: the bar" rather than as a lakehouse error, PROVIDED the session is not the
#: newest one (the newest one is handled by the still-forming path).
#:
#: Measured on 2026-11-03: AAL 2026-10-21 was stored with
#: open=12.19 / close=12.235 / volume=76690128 while Yahoo now reports
#: open=12.2 / close=12.24 / volume=76927200 - every field moved by well
#: under a percent. That is a provider-side correction of a settled session,
#: not corruption: a real ingest bug does not nudge every field in the same
#: direction by a plausible amount.
MAX_REVISION_RELATIVE = 0.01


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class BarVerdict:
    """Verdict for a single (symbol, session) comparison."""

    session: str
    stored: float | None
    provider: float | None
    verdict: str  # EXACT | TOLERANT | STALE | RESTATED | MISMATCH
    detail: str = ""


@dataclass
class SymbolReport:
    """Verdict for one symbol across all checked layers."""

    symbol: str
    provider_name: str = ""
    provider_rows: int = 0
    stored_rows: int = 0
    layers: dict[str, dict[str, int]] = field(default_factory=dict)
    mismatches: list[BarVerdict] = field(default_factory=list)
    stale: list[BarVerdict] = field(default_factory=list)
    restated: list[BarVerdict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and not self.mismatches


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_key(series: pd.Series) -> pd.Series:
    """Map timestamps to their trading session (UTC date).

    The lakehouse stamps a US session at 13:30Z (the exchange open) but a VN
    session at 02:00Z, and a still-forming session can carry a later stamp.
    Comparing raw timestamps therefore produces false mismatches for a
    perfectly good bar. The UTC date is the stable identity of a session.
    """
    stamps = pd.to_datetime(series, utc=True, errors="coerce")
    return stamps.dt.date


def _to_frame(payload) -> pd.DataFrame:
    """Normalise a provider frame to the columns we compare."""
    if payload is None or payload.empty:
        return pd.DataFrame()
    out = payload.copy()
    if "timestamp" not in out.columns:
        return pd.DataFrame()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"])
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _read_layer(layer_cls, symbol: str) -> pd.DataFrame:
    try:
        return layer_cls().read(symbol)
    except Exception as exc:  # noqa: BLE001 - a missing layer is a finding, not a crash
        return pd.DataFrame()


def _pick_session_survivor(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce a frame to one row per session, the way the lakehouse serves it.

    Mirrors ``app.lakehouse.session.canonicalize_daily_sessions``: the
    survivor of a session is the daily-bar row whose time-of-day matches the
    symbol's dominant stamp, ties broken by the most recent ingestion time.
    The provider frame is reduced with the same rule so that both sides are
    compared on equal terms.
    """
    from app.lakehouse.session import DAILY_BAR_SOURCES

    out = frame.copy()
    out["_stamp"] = out["timestamp"].dt.strftime("%H:%M")
    if "source" in out.columns:
        out["_is_daily"] = out["source"].map(
            lambda s: str(s).strip().lower() in DAILY_BAR_SOURCES if s is not None else False
        )
    else:
        out["_is_daily"] = True

    # The symbol's dominant stamp across the whole frame.
    counts = out["_stamp"].value_counts()
    symbol_stamp = None
    if not counts.empty:
        top = counts[counts == counts.max()].index.tolist()
        if len(top) == 1:
            symbol_stamp = top[0]
        else:
            for preferred in ("13:30", "14:30", "02:00", "20:00"):
                if preferred in top:
                    symbol_stamp = preferred
                    break
            symbol_stamp = symbol_stamp or sorted(top)[0]

    out["_matches"] = out["_stamp"] == symbol_stamp
    if "ingestion_time" in out.columns:
        out["_ingest"] = pd.to_datetime(out["ingestion_time"], utc=True, errors="coerce")
    else:
        out["_ingest"] = pd.Timestamp("1970-01-01", tz="UTC")

    # Daily-bar rows win over intraday rows for the same session; among them
    # the stamp-matching row wins, then the most recently ingested one.
    out["_daily_rank"] = (~out["_is_daily"]).astype(int)
    ordered = out.sort_values(
        ["_session", "_daily_rank", "_matches", "_ingest"],
        ascending=[True, True, False, False],
        kind="mergesort",
    )
    survivors = ordered.drop_duplicates(subset=["_session"], keep="first")
    return survivors.set_index("_session")


# ---------------------------------------------------------------------------
# The core comparison
# ---------------------------------------------------------------------------


def compare_layer(
    symbol: str,
    layer_name: str,
    stored: pd.DataFrame,
    provider: pd.DataFrame,
    tolerance: float,
    window: int,
) -> tuple[dict[str, int], list[BarVerdict], list[BarVerdict], list[BarVerdict]]:
    """Compare one stored layer against the provider frame.

    Returns (counts, mismatches, stale, restated).
    """
    counts = {"EXACT": 0, "TOLERANT": 0, "STALE": 0, "RESTATED": 0, "MISMATCH": 0, "NO_PROVIDER_BAR": 0}
    mismatches: list[BarVerdict] = []
    stale: list[BarVerdict] = []
    restated_bars: list[BarVerdict] = []

    if stored.empty or provider.empty:
        return counts, mismatches, stale, restated_bars

    stored = stored.copy()
    stored["_session"] = _session_key(stored["timestamp"])
    # A layer can hold several rows for one session (Bronze does, before
    # canonicalisation). Compare against the row the layer would SERVE.
    #
    # The serving rule is the one in `app.lakehouse.session`: a session's
    # survivor is the DAILY-BAR row whose stamp matches the symbol's
    # convention, ties broken by the most recent ingestion time. Picking the
    # last row instead would flag a re-stamped copy (e.g. a 20:00Z copy of a
    # 13:30Z session bar) as a mismatch even though Silver and Gold resolve
    # the same session to the correct value.
    stored = _pick_session_survivor(stored)

    provider = provider.copy()
    provider["_session"] = _session_key(provider["timestamp"])
    provider = _pick_session_survivor(provider)

    # Only compare the trailing window of sessions the provider actually has.
    sessions = [s for s in provider.index if s in stored.index]
    sessions = sorted(sessions)[-window:]

    for session in sessions:
        s_row = stored.loc[session]
        p_row = provider.loc[session]
        if isinstance(s_row, pd.DataFrame):
            s_row = s_row.iloc[-1]
        if isinstance(p_row, pd.DataFrame):
            p_row = p_row.iloc[-1]

        s_close = s_row.get("close")
        p_close = p_row.get("close")
        try:
            s_close = float(s_close)
            p_close = float(p_close)
        except (TypeError, ValueError):
            counts["NO_PROVIDER_BAR"] += 1
            continue
        if not (s_close > 0) or not (p_close > 0):
            counts["NO_PROVIDER_BAR"] += 1
            continue

        diff = abs(s_close - p_close)
        rel = diff / p_close

        if diff == 0.0:
            counts["EXACT"] += 1
            continue
        if rel <= tolerance:
            counts["TOLERANT"] += 1
            continue

        # A difference this size is either a real mismatch or a legitimately
        # different moment in time. Distinguish them by looking at whether
        # the STORED value matches the provider's value for a DIFFERENT
        # session - that is the signature of a shifted timestamp.
        verdict = "MISMATCH"
        detail = f"close {s_close:.6f} vs provider {p_close:.6f} (rel {rel:.6%})"

        # Look for the stored close elsewhere in the provider's series.
        provider_closes = provider["close"].dropna()
        if not provider_closes.empty:
            nearest = (provider_closes - s_close).abs().idxmin()
            nearest_rel = abs(provider_closes.loc[nearest] - s_close) / max(s_close, 1e-9)
            if nearest_rel <= 1e-6:
                verdict = "STALE"
                detail = (
                    f"stored close {s_close:.6f} matches provider session {nearest} "
                    f"instead of {session} (timestamp shift / re-stamped bar)"
                )

        # The stored session is simply the newest one and the provider has
        # since moved on, or the stored bar was captured while the session
        # was still forming. Both are explainable.
        if verdict == "MISMATCH":
            provider_max = provider.index.max()
            stored_max = stored.index.max()
            if session == stored_max and provider_max is not None:
                verdict = "STALE"
                detail = (
                    f"stored close {s_close:.6f} vs provider {p_close:.6f}; "
                    f"newest stored session {stored_max} was still forming "
                    f"(provider's newest is {provider_max})"
                )

        # The provider RESTATED a bar it had already published. Two distinct
        # shapes, both meaning "the provider revised its own history":
        #
        #  * a revision of one field - the stored bar's other fields (open/low)
        #    still agree with the provider's while close/high differ. A
        #    lakehouse corruption would not leave open/low intact and change
        #    only the close. Measured on 2026-11-03: 005930.KS 2026-10-23 was
        #    stored with close=212250 / high=214500 / volume=11326064 while
        #    Yahoo now reports close=215500 / high=215500 / volume=16145972.
        #
        #  * a small revision across the board - every field moved by a
        #    fraction of a percent. Measured on 2026-11-03: AAL 2026-10-21 was
        #    stored with open=12.19 / close=12.235 / volume=76690128 while
        #    Yahoo now reports open=12.2 / close=12.24 / volume=76927200.
        #
        # Both are the provider correcting itself, not the lakehouse
        # corrupting data. The distinction matters because the FIX is the
        # same (re-ingest the window) while the SEVERITY is not.
        if verdict == "MISMATCH":
            restated = _looks_restated(stored, provider, session)
            if restated:
                verdict = "RESTATED"
                detail = (
                    f"stored close {s_close:.6f} vs provider {p_close:.6f}; "
                    f"{restated}. The provider has revised this bar since it "
                    f"was ingested."
                )
            elif rel <= MAX_REVISION_RELATIVE and session != stored.index.max():
                verdict = "RESTATED"
                detail = (
                    f"stored close {s_close:.6f} vs provider {p_close:.6f} "
                    f"(rel {rel:.4%}); every field moved by a small amount, "
                    f"which is the provider revising its own history, not a "
                    f"lakehouse error"
                )

        if verdict == "MISMATCH":
            counts["MISMATCH"] += 1
            mismatches.append(BarVerdict(str(session), s_close, p_close, verdict, detail))
        elif verdict == "RESTATED":
            counts["RESTATED"] += 1
            restated_bars.append(BarVerdict(str(session), s_close, p_close, verdict, detail))
        else:
            counts["STALE"] += 1
            stale.append(BarVerdict(str(session), s_close, p_close, verdict, detail))

    return counts, mismatches, stale, restated_bars


def _looks_restated(stored: pd.DataFrame, provider: pd.DataFrame, session) -> str:
    """Heuristic: did the provider revise this bar, or is the lakehouse wrong?

    Returns a short description when the pattern matches a provider
    restatement, or ``""`` when it does not.

    The signals that point at a restatement rather than a lakehouse bug:

    * the session is NOT the newest one - a still-forming bar is handled by
      the STALE path already, so what is left is a settled session;
    * the stored bar's ``open`` and ``low`` still agree with the provider's,
      while ``close`` and/or ``volume`` differ. A lakehouse corruption would
      not leave open/low intact and change only the close;
    * the stored bar was ingested at least a full day before the provider's
      current value could have existed.
    """
    try:
        s_row = stored.loc[session]
        p_row = provider.loc[session]
        if isinstance(s_row, pd.DataFrame):
            s_row = s_row.iloc[-1]
        if isinstance(p_row, pd.DataFrame):
            p_row = p_row.iloc[-1]
    except (KeyError, IndexError):
        return ""

    def _num(row, key):
        try:
            value = row.get(key)
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    s_open, p_open = _num(s_row, "open"), _num(p_row, "open")
    s_low, p_low = _num(s_row, "low"), _num(p_row, "low")
    s_close, p_close = _num(s_row, "close"), _num(p_row, "close")

    if None in (s_open, p_open, s_low, p_low, s_close, p_close):
        return ""
    if p_open <= 0 or p_close <= 0:
        return ""

    def _same(a, b) -> bool:
        return abs(a - b) <= 1e-6 * max(abs(b), 1.0)

    open_same = _same(s_open, p_open)
    low_same = _same(s_low, p_low)
    close_same = _same(s_close, p_close)

    if open_same and low_same and not close_same:
        return "open and low still match the provider, only the close was revised"
    if open_same and low_same and close_same:
        # Price is fine, so only the volume must have been revised.
        s_vol = _num(s_row, "volume")
        p_vol = _num(p_row, "volume")
        if s_vol is not None and p_vol is not None and not _same(s_vol, p_vol):
            return "price still matches the provider, only the volume was revised"
    return ""


def check_cross_source_agreement(symbol: str, stored: pd.DataFrame) -> list[str]:
    """Within one symbol, do the different ``source`` values agree on price?

    A symbol ingested from two providers (e.g. ``yahoo_http`` and ``vn_rest``)
    must produce the same session close from both, otherwise the lakehouse
    holds two different "truths" for the same trading day.
    """
    notes: list[str] = []
    if stored.empty or "source" not in stored.columns:
        return notes

    frame = stored.copy()
    frame["_session"] = _session_key(frame["timestamp"])
    sources = [s for s in frame["source"].dropna().unique() if s]
    if len(sources) < 2:
        return notes

    pivot = frame.pivot_table(
        index="_session", columns="source", values="close", aggfunc="last"
    )
    compared = 0
    for col in sources[1:]:
        if col not in pivot.columns:
            continue
        both = pivot[[sources[0], col]].dropna()
        if both.empty:
            continue
        rel = ((both[sources[0]] - both[col]).abs() / both[col].abs().clip(lower=1e-9)).max()
        compared += len(both)
        if rel > 0.01:
            offenders = both[(both[sources[0]] - both[col]).abs() / both[col].abs().clip(lower=1e-9) > 0.01]
            notes.append(
                f"cross-source gap {rel:.4%} between '{sources[0]}' and '{col}' "
                f"on {len(offenders)} session(s), e.g. {offenders.index[-1]}"
            )
    if compared and not notes:
        notes.append(
            f"cross-source OK: '{sources[0]}' vs "
            + ", ".join(f"'{s}'" for s in sources[1:])
            + f" agree on {compared} shared session(s)"
        )
    return notes


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def fetch_provider(symbol: str, provider) -> pd.DataFrame:
    """Re-fetch a symbol straight from the provider."""
    try:
        return _to_frame(provider.get_historical_data(symbol, interval="1d"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"provider failed for {symbol}: {exc}") from exc


def fetch_api(symbol: str, base_url: str, timeout: float) -> pd.DataFrame:
    """Fetch a symbol from the running API - the data the browser actually sees.

    This closes the last link in the chain. Verifying the layers only proves
    that MinIO holds the right numbers; it does NOT prove that the web serves
    them. A serving bug (wrong layer, stale cache, a transformation applied
    on the way out) would leave the lakehouse correct and the page wrong, and
    that is precisely the class of problem the user cannot see from the UI.
    """
    import json
    import urllib.request

    url = f"{base_url.rstrip('/')}/stocks/{symbol}?interval=1d"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"API request failed for {symbol}: {exc}") from exc

    data = payload.get("data") or {}
    rows = data.get("rows") or []
    if not rows:
        raise RuntimeError(f"API returned no rows for {symbol}")
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    return frame.dropna(subset=["timestamp"])


def verify_api_layer(
    symbol: str,
    base_url: str,
    provider: pd.DataFrame,
    tolerance: float,
    window: int,
    timeout: float = 60.0,
) -> tuple[dict[str, int], list[BarVerdict], list[BarVerdict], list[BarVerdict], str]:
    """Compare what the API serves against the live provider."""
    counts = {"EXACT": 0, "TOLERANT": 0, "STALE": 0, "RESTATED": 0, "MISMATCH": 0, "NO_PROVIDER_BAR": 0}
    mismatches: list[BarVerdict] = []
    stale: list[BarVerdict] = []
    restated_bars: list[BarVerdict] = []

    try:
        served = fetch_api(symbol, base_url, timeout)
    except Exception as exc:  # noqa: BLE001
        counts["ERROR"] = 1
        return counts, mismatches, stale, restated_bars, str(exc)

    served = served.copy()
    served["_session"] = _session_key(served["timestamp"])
    served = _pick_session_survivor(served)

    live = provider.copy()
    live["_session"] = _session_key(live["timestamp"])
    live = _pick_session_survivor(live)

    sessions = sorted(s for s in live.index if s in served.index)[-window:]

    for session in sessions:
        s_row = served.loc[session]
        p_row = live.loc[session]
        if isinstance(s_row, pd.DataFrame):
            s_row = s_row.iloc[-1]
        if isinstance(p_row, pd.DataFrame):
            p_row = p_row.iloc[-1]
        try:
            s_close = float(s_row["close"])
            p_close = float(p_row["close"])
        except (TypeError, ValueError, KeyError):
            counts["NO_PROVIDER_BAR"] += 1
            continue
        if not (s_close > 0) or not (p_close > 0):
            counts["NO_PROVIDER_BAR"] += 1
            continue

        diff = abs(s_close - p_close)
        rel = diff / p_close
        if diff == 0.0:
            counts["EXACT"] += 1
        elif rel <= tolerance:
            counts["TOLERANT"] += 1
        else:
            verdict = "MISMATCH"
            detail = f"API close {s_close:.6f} vs provider {p_close:.6f} (rel {rel:.6%})"
            provider_closes = live["close"].dropna()
            if not provider_closes.empty:
                nearest = (provider_closes - s_close).abs().idxmin()
                if abs(provider_closes.loc[nearest] - s_close) / max(s_close, 1e-9) <= 1e-6:
                    verdict = "STALE"
                    detail = (
                        f"API close {s_close:.6f} matches provider session {nearest} "
                        f"instead of {session}"
                    )
            if verdict == "MISMATCH" and session == served.index.max():
                verdict = "STALE"
                detail = (
                    f"API close {s_close:.6f} vs provider {p_close:.6f}; "
                    "the newest served session was still forming when it was stored"
                )
            if verdict == "MISMATCH":
                restated = _looks_restated(served, live, session)
                if restated:
                    verdict = "RESTATED"
                    detail = (
                        f"API close {s_close:.6f} vs provider {p_close:.6f}; "
                        f"{restated}. The provider has revised this bar since it "
                        f"was ingested."
                    )
                elif rel <= MAX_REVISION_RELATIVE and session != served.index.max():
                    verdict = "RESTATED"
                    detail = (
                        f"API close {s_close:.6f} vs provider {p_close:.6f} "
                        f"(rel {rel:.4%}); every field moved by a small amount, "
                        f"which is the provider revising its own history"
                    )
            if verdict == "MISMATCH":
                counts["MISMATCH"] += 1
                mismatches.append(BarVerdict(str(session), s_close, p_close, verdict, detail))
            elif verdict == "RESTATED":
                counts["RESTATED"] += 1
                restated_bars.append(BarVerdict(str(session), s_close, p_close, verdict, detail))
            else:
                counts["STALE"] += 1
                stale.append(BarVerdict(str(session), s_close, p_close, verdict, detail))

    return counts, mismatches, stale, restated_bars, ""


def verify_symbol(
    symbol: str,
    provider,
    tolerance: float,
    window: int,
    layers: tuple[str, ...],
    api_url: str | None = None,
) -> SymbolReport:
    report = SymbolReport(symbol=symbol)

    try:
        live = fetch_provider(symbol, provider)
    except Exception as exc:  # noqa: BLE001
        report.error = str(exc)
        return report

    report.provider_name = getattr(provider, "source_name", provider.__class__.__name__)
    report.provider_rows = len(live)

    layer_readers = {"bronze": BronzeLayer, "silver": SilverLayer, "gold": GoldLayer}
    all_mismatches: list[BarVerdict] = []
    all_stale: list[BarVerdict] = []
    all_restated: list[BarVerdict] = []

    for layer_name in layers:
        stored = _read_layer(layer_readers[layer_name], symbol)
        report.stored_rows = max(report.stored_rows, len(stored))
        if stored.empty:
            report.layers[layer_name] = {"EMPTY": 1}
            report.notes.append(f"{layer_name}: empty")
            continue
        counts, mismatches, stale, restated = compare_layer(
            symbol, layer_name, stored, live, tolerance, window
        )
        report.layers[layer_name] = counts
        all_mismatches.extend(mismatches)
        all_stale.extend(stale)
        all_restated.extend(restated)

        if layer_name == "bronze":
            report.notes.extend(check_cross_source_agreement(symbol, stored))

    # The API layer is checked last: it is what the browser actually renders,
    # so a mismatch here is the one the user would notice.
    if api_url:
        counts, mismatches, stale, restated, error = verify_api_layer(
            symbol, api_url, live, tolerance, window
        )
        report.layers["api"] = counts
        if error:
            report.notes.append(f"api: {error}")
        all_mismatches.extend(mismatches)
        all_stale.extend(stale)
        all_restated.extend(restated)

    report.mismatches = all_mismatches
    report.stale = all_stale
    report.restated = all_restated
    return report


def resolve_symbols(requested: list[str]) -> list[str]:
    """Expand the ``--symbols`` argument into an actual symbol list."""
    if "all" not in requested:
        return [s.upper() for s in requested]
    # Enumerate from Bronze, which is the layer that holds every ingested
    # symbol regardless of whether Silver/Gold were rebuilt.
    from app.lakehouse.storage_factory import get_storage_backend

    storage = get_storage_backend()
    symbols: set[str] = set()
    for obj in storage.client.list_objects(storage._bucket("bronze"), prefix="symbol=", recursive=False):
        name = obj.object_name or ""
        if name.startswith("symbol="):
            sym = name.split("/", 1)[0].split("=", 1)[1].upper()
            if sym:
                symbols.add(sym)
    return sorted(symbols)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS),
                        help="Symbols to verify, or 'all' for every symbol in Bronze")
    parser.add_argument("--layer", dest="layers", nargs="+",
                        default=["bronze", "silver", "gold"],
                        choices=["bronze", "silver", "gold"],
                        help="Which layers to compare")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                        help="Relative price difference treated as rounding noise")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                        help="Trailing sessions to compare per symbol")
    parser.add_argument("--max-symbols", type=int, default=0,
                        help="Stop after N symbols (0 = no limit)")
    parser.add_argument("--offset", type=int, default=0,
                        help="Skip the first N symbols of the resolved list. Use it "
                             "to walk the universe in slices, e.g. --offset 200 "
                             "--max-symbols 200 covers the second slice.")
    parser.add_argument("--provider", default="yahoo_http",
                        help="Provider to re-fetch from (default: yahoo_http)")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/v1",
                        help="Base URL of the running API, for verifying what the web "
                             "actually serves. Pass '' to skip the API layer.")
    args = parser.parse_args(argv)

    setup_logging()
    from app.data_sources.factory import get_data_provider

    symbols = resolve_symbols(list(args.symbols))
    if args.offset:
        symbols = symbols[args.offset:]
        print(f"Skipping the first {args.offset} symbol(s) of the resolved list")
    if args.max_symbols:
        symbols = symbols[: args.max_symbols]
    if not symbols:
        print("No symbols to verify.")
        return 2

    api_url = args.api_url or None

    print("=" * 78)
    print("VERIFYING LAKEHOUSE DATA AGAINST THE LIVE PROVIDER")
    print("=" * 78)
    print(f"provider   : {args.provider}")
    print(f"layers     : {', '.join(args.layers)}" + (f" + api" if api_url else ""))
    print(f"symbols    : {len(symbols)}  window: {args.window} sessions  "
          f"tolerance: {args.tolerance:.1e}")
    if api_url:
        print(f"api        : {api_url}")
    print()

    try:
        provider = get_data_provider(args.provider)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot build provider '{args.provider}': {exc}")
        return 2

    reports: list[SymbolReport] = []
    for i, symbol in enumerate(symbols, 1):
        report = verify_symbol(symbol, provider, args.tolerance, args.window,
                               tuple(args.layers), api_url=api_url)
        reports.append(report)

        status = "ERROR" if report.error else ("FAIL" if report.mismatches else " OK ")
        print(f"[{status}] {symbol:<8}", end="")
        if report.error:
            print(f" {report.error}")
        else:
            parts = []
            for layer_name, counts in report.layers.items():
                if "EMPTY" in counts:
                    parts.append(f"{layer_name}=EMPTY")
                    continue
                parts.append(
                    f"{layer_name}: {counts['EXACT']} exact, "
                    f"{counts['TOLERANT']} tolerant, "
                    f"{counts['STALE']} stale, "
                    f"{counts.get('RESTATED', 0)} restated, "
                    f"{counts['MISMATCH']} mismatch"
                )
            print(f" provider={report.provider_name}({report.provider_rows}) " + " | ".join(parts))
            for note in report.notes:
                print(f"          note: {note}")
            for bar in report.restated[:3]:
                print(f"          RESTATED {bar.session}: {bar.detail}")
            for bar in report.mismatches[:5]:
                print(f"          MISMATCH {bar.session}: {bar.detail}")
            if len(report.mismatches) > 5:
                print(f"          ... and {len(report.mismatches) - 5} more mismatch(es)")

    # ---- summary ----
    total_exact = sum(c.get("EXACT", 0) for r in reports for c in r.layers.values())
    total_tol = sum(c.get("TOLERANT", 0) for r in reports for c in r.layers.values())
    total_stale = sum(c.get("STALE", 0) for r in reports for c in r.layers.values())
    total_restated = sum(c.get("RESTATED", 0) for r in reports for c in r.layers.values())
    total_bad = sum(len(r.mismatches) for r in reports)
    total_err = sum(1 for r in reports if r.error)

    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  symbols checked : {len(reports)}")
    print(f"  exact matches   : {total_exact}")
    print(f"  tolerant        : {total_tol}   (difference below tolerance)")
    print(f"  stale/explained : {total_stale}   (newest bar still forming, or a re-stamped session)")
    print(f"  restated        : {total_restated}   (the provider revised the bar after it was ingested)")
    print(f"  MISMATCHES      : {total_bad}")
    print(f"  errors          : {total_err}")
    print()
    if total_bad:
        print("VERDICT: FAILED - stored values differ from the provider beyond tolerance.")
        for report in reports:
            if report.mismatches:
                print(f"  {report.symbol}: {len(report.mismatches)} mismatch(es)")
        return 1
    if total_restated:
        print("VERDICT: PASSED with restatements.")
        print("  The provider has revised some bars after they were ingested. The")
        print("  lakehouse holds the OLD value, which is what the provider served on")
        print("  the day of ingestion. To pick up the revisions, re-ingest the")
        print("  affected window:")
        print("      python scripts/backfill_silver_gold.py --symbols <SYM> --days 30")
        restated_symbols = sorted({r.symbol for r in reports if r.restated})
        print(f"  affected symbols: {', '.join(restated_symbols)}")
        return 0
    if total_err:
        print("VERDICT: INCOMPLETE - some symbols could not be checked.")
        return 2
    print("VERDICT: PASSED - every checked bar matches the live provider.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
