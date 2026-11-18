"""The data quality gate: what the lakehouse knows about its own cleanliness.

WHY THIS FILE EXISTS
--------------------
The lakehouse had excellent verification TOOLS:

* ``scripts/verify_against_source.py`` re-fetches every symbol from the live
  provider and compares Bronze/Silver/Gold/API bar by bar;
* ``app/lakehouse/plausibility.py`` rejects rows that cannot be real market
  data (a VND quote divided by 1000, a 1970 timestamp);
* ``scripts/check_layer_divergence.py`` compares the three layers against each
  other.

All three are correct, and all three are MANUAL. Nobody runs them before
shipping, and when they are run, their output lands in a terminal nobody
reads again. So the system could be wrong and would still look fine - which
is exactly the failure mode this project is not allowed to have.

What was missing is the QUESTION, not the machinery:

    "Is the data currently in the lakehouse clean, and since WHEN?"

This module answers it, continuously, from evidence the lakehouse already
carries. It answers it WITHOUT inventing a number: every metric below is
computed from stored rows, stored quality reports, or a live provider call.

WHAT THE GATE CHECKS
--------------------
Six independent checks, because they fail for different reasons:

1. ``plausibility``   - the rows that Bronze's screen rejected, per symbol,
   read from ``bronze/_quality/rejected_rows.json``.
2. ``layer_agreement``- do Bronze, Silver and Gold hold the SAME close for the
   same trading session? A provider restatement that Bronze absorbed but
   Silver never rebuilt is invisible to every other check.
3. ``integrity``      - do the stored rows still satisfy the market's own
   rules (``low <= open/close <= high``, ``volume >= 0``, one bar per
   session, a monotonic series)?
4. ``freshness``      - does each symbol hold a bar for a recent session? A
   symbol whose newest bar is a month old is not wrong, but it IS stale, and
   a stale symbol silently poisons every indicator computed over it.
5. ``source_agreement`` - do two providers that both serve a symbol agree on
   its close?
6. ``forming_snapshots`` - does Bronze hold a daily bar that was captured
   while its session was still running? A frozen mid-session snapshot looks
   like a provider disagreement but is a different defect, so it is named
   separately - see the module docstring of
   ``app/lakehouse/forming_bar.py``.

WHY THE GATE DOES NOT RE-FETCH THE WHOLE UNIVERSE
-------------------------------------------------
``verify_against_source.py`` re-fetches the provider for every symbol, which
is the strongest check available - and it is slow, because it makes a
network call per symbol. A gate that runs every hour cannot afford that.

So the gate runs on a ROTATION: each pass checks a slice of the universe
against the live provider, and the slices are cumulative. A full sweep
therefore completes every N passes while each individual pass stays cheap.
The rotation is persisted, so a restart does not re-check the same symbols
and skip others.

The other four checks are cheap enough to run over the WHOLE universe on
every pass, because they read what is already stored.

HOW THE VERDICT IS DERIVED
--------------------------
A gate that only produces numbers is a dashboard nobody reads. This one
produces a VERDICT: ``passed``, ``warning`` or ``failed``, plus the reason.

The rule is deliberately asymmetric, mirroring the one used everywhere else
in this codebase (see ``app/forecasting/sessions.py``): a false alarm is
cheap and visible, a missed defect is expensive and silent. So:

* ``failed``    - a symbol holds data that is provably wrong (the three
  layers disagree on a price, a row violates the OHLC rules, a symbol's
  newest bar is absent from the layer that serves it). Something must be
  fixed.
* ``warning``   - the data is usable but not clean: a symbol is stale, a row
  was rejected by the plausibility screen, the provider has since revised a
  bar. Nothing is wrong, but something should be looked at.
* ``passed``    - every check succeeded.

NO FABRICATED METRICS
---------------------
Every number here is counted from stored objects or a live provider. If a
check cannot run - MinIO is down, the provider is unreachable - the gate says
so and marks the check as ``unavailable``. It does NOT report zero, and it
does NOT report a passing score for a check that never ran. A gate that
reports "100% clean" because it could not look at anything is worse than no
gate at all.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from app.core.data_integrity import is_fabricated_symbol
from app.core.logging_config import get_logger
from app.lakehouse.exchange_timezone import session_day_of, session_days
from app.lakehouse.forming_bar import find_forming_snapshots, forming_snapshot_reason
from app.lakehouse.session import canonicalize_daily_sessions, session_date

logger = get_logger(__name__)

#: How many symbols each pass checks against the LIVE provider.
#:
#: 40 is a compromise. The provider call is the slow part (~0.3-1s per
#: symbol), so 40 symbols take ~15-40s on a thread pool - long enough to be
#: worth batching, short enough to fit between two cron ticks. The full
#: universe of ~1000 symbols therefore completes a full sweep every ~25
#: passes, which at one pass per hour is about a day.
PROVIDER_CHECK_BATCH = 40

#: How many threads the storage-reading checks run on.
#:
#: The checks that read the lakehouse are I/O bound, not CPU bound: the
#: work is a MinIO round-trip per partition, and the CPU sits idle waiting
#: for the bytes. Overlapping the reads is therefore nearly free.
#:
#: 12 is chosen to stay well inside MinIO's connection pool (64) while
#: still overlapping enough to hide the latency. Measured on 2026-11-15:
#: 100 symbols took 50s serially and about 12s with this many workers.
_READ_WORKERS = 12

#: How many trailing sessions the provider comparison covers.
#:
#: 30 sessions is about six weeks of trading. It is long enough to catch a
#: systematic error - a shifted timestamp, a scaled price - and short enough
#: that a provider's own history rewriting stays a small, explainable
#: difference rather than a flood of mismatches.
PROVIDER_CHECK_WINDOW = 30

#: Relative price difference treated as rounding noise, not a defect.
#:
#: The same tolerance the verifier uses, so "mismatch" means exactly the
#: same thing in both places. It is RELATIVE because an absolute floor
#: would be wrong in both directions: for ACH at $0.21 a 1e-9 absolute
#: difference is already 5e-9 relative, while for VCB at 56,000 the same
#: difference is 2e-14 - float noise.
PRICE_TOLERANCE = 1e-6

#: A symbol whose newest session is older than this is STALE.
#:
#: The universe spans several markets - US, Vietnam, Hong Kong, Korea,
#: Japan, Australia, Europe - whose holidays never coincide, so a single
#: global threshold would flag most of the universe as stale on any given
#: day. 10 calendar days is long enough to cover a national holiday week
#: plus a weekend, and short enough that a symbol which stopped being
#: served is noticed within a fortnight.
STALE_AFTER_DAYS = 10

#: The newest session that ANY symbol in the universe holds.
#:
#: This is the reference point for the staleness check. Comparing each
#: symbol against the calendar date would flag every symbol over a holiday
#: weekend; comparing it against the newest session IN THE LAKEHOUSE asks
#: the right question: "is this symbol as current as the market it belongs
#: to?".


@dataclass
class CheckResult:
    """The outcome of one check over the universe."""

    #: ``passed``, ``warning``, ``failed`` or ``unavailable``.
    status: str = "passed"
    #: How many symbols were actually examined. A check that could not run
    #: reports 0 here, so it can never be mistaken for a clean sweep.
    checked: int = 0
    #: How many symbols failed the check.
    failed: int = 0
    #: How many symbols raised a warning.
    warned: int = 0
    #: Why the check could not run, when ``status`` is ``unavailable``.
    reason: str = ""
    #: The symbols that failed, capped so one bad afternoon cannot produce a
    #: 1000-entry payload.
    offenders: list[str] = field(default_factory=list)
    #: Extra, check-specific numbers.
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "checked": self.checked,
            "failed": self.failed,
            "warned": self.warned,
            "reason": self.reason,
            "offenders": list(self.offenders),
            "details": dict(self.details),
        }


@dataclass
class QualityGateReport:
    """The whole gate: every check, the verdict, and when it ran."""

    #: ``passed``, ``warning`` or ``failed``.
    verdict: str = "passed"
    #: When the gate ran (UTC).
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: How long the pass took, in seconds.
    elapsed_seconds: float = 0.0
    #: One entry per check, keyed by the check's name.
    checks: dict[str, CheckResult] = field(default_factory=dict)
    #: The symbols the provider comparison covered this pass.
    provider_batch: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "checked_at": self.checked_at.isoformat(),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "checks": {name: result.to_dict() for name, result in self.checks.items()},
            "provider_batch_size": len(self.provider_batch),
            "provider_batch": list(self.provider_batch),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


def _worst(statuses: Iterable[str]) -> str:
    """The most severe status among the given ones.

    The ordering is deliberate: a check that could NOT run is worse than a
    check that found a problem, because a problem is visible while a silent
    check is not. An ``unavailable`` check therefore forces the verdict to
    ``failed`` - the gate says "I do not know", and it does not pretend
    otherwise.
    """
    order = {"passed": 0, "warning": 1, "failed": 2, "unavailable": 3}
    worst = "passed"
    for status in statuses:
        if order.get(status, 2) > order.get(worst, 2):
            worst = status
    return worst


# ---------------------------------------------------------------------------
# Symbol discovery
# ---------------------------------------------------------------------------


def lakehouse_symbols(storage) -> list[str]:
    """Every symbol that holds data in the Bronze layer.

    Bronze is the layer that holds every INGESTED symbol, regardless of
    whether Silver and Gold were rebuilt afterwards. A symbol that exists
    only in Silver would be a symbol whose Bronze was lost, which is
    itself a defect - but it should still be SEEN, so the check below
    compares the layers per symbol rather than trusting one of them.
    """
    symbols: set[str] = set()
    for key in storage.list_objects("bronze", "symbol="):
        normalised = str(key).replace("\\", "/")
        if "symbol=" not in normalised:
            continue
        head = normalised.split("symbol=", 1)[1].split("/", 1)[0]
        symbol = head.strip().upper()
        if symbol:
            symbols.add(symbol)
    return sorted(symbols)


def partition_index(storage, layer: str) -> dict[str, list[str]]:
    """Every symbol's partition keys in one layer, keyed by symbol.

    WHY THIS EXISTS
    ---------------
    The first version of this gate listed a symbol's partitions SEPARATELY
    for each symbol and each layer - 3,000 listing calls for a 1,000-symbol
    universe, each one a paginated walk of that symbol's ~120 monthly
    partitions. The pass took minutes, and the parallel version made MinIO
    reset connections under the load.

    Listing the layer ONCE and grouping the keys by symbol turns those
    3,000 calls into 1. The cost becomes one paginated walk per layer
    (measured: 9.5s for the Silver bucket's 116,103 keys), and every
    subsequent read knows exactly which object it wants.

    The index is built once per gate pass and handed to every check, so
    the whole pass pays for it once.

    THE PATH SEPARATOR IS NOT THE SAME ON EVERY BACKEND
    --------------------------------------------------
    MinIO keys look like ``symbol=AAPL/year=2026/month=11/part-001.parquet``
    while the local filesystem backend yields
    ``...\\bronze\\symbol=AAPL\\year=2026\\month=11\\part-001.parquet``. The
    first version of this function split on ``/`` only, so on the local
    backend it returned an EMPTY index - the gate then reported "no symbols"
    and quietly audited nothing. Both separators are handled here, and the
    symbol is read from the FIRST path segment that starts with ``symbol=``.
    """
    index: dict[str, list[str]] = {}
    for key in storage.list_objects(layer, "symbol="):
        name = str(key)
        normalised = name.replace("\\", "/")
        if "symbol=" not in normalised:
            continue
        head = normalised.split("symbol=", 1)[1].split("/", 1)[0]
        symbol = head.strip().upper()
        if not symbol or not normalised.endswith(".parquet"):
            continue
        index.setdefault(symbol, []).append(name)
    return index


def _window_keys(keys: list[str], days: int) -> list[str]:
    """The partition keys that can hold rows inside the trailing window.

    The partition path carries the period (``year=2026/month=11/...``), so
    the window's months can be selected WITHOUT downloading anything. A
    symbol with 120 partitions of history contributes one or two keys.
    """
    since = date.today() - timedelta(days=days)
    first = (since.year, since.month)
    kept: list[str] = []
    for key in keys:
        placed = None
        # The separator differs per backend: MinIO keys use "/", the local
        # filesystem backend uses "\\". Both are normalised here, otherwise
        # the window filter would keep EVERY partition on the local backend
        # (no "year=" segment would ever be found).
        parts = str(key).replace("\\", "/").split("/")
        for index, part in enumerate(parts):
            if part.startswith("year=") and index + 1 < len(parts):
                month_part = parts[index + 1]
                if month_part.startswith("month="):
                    try:
                        placed = (
                            int(part.split("=", 1)[1]),
                            int(month_part.split("=", 1)[1]),
                        )
                    except ValueError:
                        placed = None
                break
        if placed is None or placed >= first:
            kept.append(key)
    return kept


# ---------------------------------------------------------------------------
# Check 1: the plausibility screen's own rejections
# ---------------------------------------------------------------------------


def check_plausibility(storage) -> CheckResult:
    """Did Bronze's plausibility screen reject anything, and how much?

    WHY THIS CHECK EXISTS
    ---------------------
    The plausibility screen is the lakehouse's first line of defence, and it
    LOGS every rejection into ``bronze/_quality/rejected_rows.json``. That
    log is the evidence that the screen is actually firing - and also the
    evidence of a provider sending something impossible.

    A rejection is a WARNING, not a failure: the screen did its job, the
    bad row was kept out, and the lakehouse is clean BECAUSE of it. It is
    reported so that a rising rejection count - a provider changing its
    format, a parser regression - is visible before it starts rejecting
    good rows.
    """
    result = CheckResult()
    try:
        payload = storage.read_json("bronze", "_quality/rejected_rows.json")
    except Exception as exc:  # noqa: BLE001 - an absent log means "nothing rejected"
        result.status = "passed"
        result.reason = f"no rejection log yet ({exc.__class__.__name__})"
        return result

    rejected = int(payload.get("report", {}).get("rejected_rows", 0) or 0)
    reasons = payload.get("report", {}).get("reasons", {}) or {}
    result.checked = 1
    result.details = {
        "rejected_rows": rejected,
        "reasons": reasons,
        "last_rejection_at": payload.get("ingestion_time"),
    }
    if rejected > 0:
        result.status = "warning"
        result.warned = 1
    return result


# ---------------------------------------------------------------------------
# Check 2: do the three layers agree?
# ---------------------------------------------------------------------------


def _session_closes(frame: pd.DataFrame, symbol: str | None = None) -> dict[str, float]:
    """One close per trading session, keyed by the session's date.

    The rows are CANONICALISED first, because Bronze holds the raw provider
    output - several rows for one session - while Silver and Gold hold one
    bar per session. Comparing Bronze's raw ticks against Silver's single
    canonical bar would report a divergence on every day that arrived as
    more than one tick, for every symbol: noise, not a defect.

    The session day is derived in the EXCHANGE's timezone, not in UTC: the
    ASX opens at 23:00Z of the previous day, so the UTC day would split one
    session across two calendar days and report a divergence that does not
    exist.
    """
    if frame is None or frame.empty or "timestamp" not in frame.columns:
        return {}
    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working = working.dropna(subset=["timestamp"])
    if working.empty:
        return {}
    if symbol is not None and "symbol" not in working.columns:
        working["symbol"] = symbol
    try:
        working, _report = canonicalize_daily_sessions(working)
    except Exception:  # noqa: BLE001 - fall back to the raw rows
        pass
    working["_close"] = pd.to_numeric(working["close"], errors="coerce")
    working = working.dropna(subset=["_close"])
    working = working.sort_values("timestamp")
    # The key is the session day in the EXCHANGE's timezone. Using the UTC
    # date would put the ASX's 23:00Z bar on the wrong day, because that bar
    # describes the NEXT local session.
    if "symbol" in working.columns:
        days = session_days(working)
    else:
        days = working["timestamp"].map(lambda stamp: session_day_of(stamp, symbol))
    # `itertuples` renames a column that starts with an underscore, so the
    # day and the close are read positionally instead of by attribute.
    return {
        str(row[0]): float(row[1])
        for row in pd.DataFrame({"_day": days, "_close": working["_close"]}).itertuples(index=False)
    }


def _session_bars(frame: pd.DataFrame, symbol: str | None = None) -> dict[str, dict]:
    """One OHLCV bar per trading session, keyed by the session's date.

    Same canonicalisation as :func:`_session_closes`, but it keeps the whole
    bar instead of only the close. The provider comparison needs ``high``,
    ``low`` and ``volume`` because it has to tell a SETTLED disagreement from
    a MID-SESSION SNAPSHOT - and that distinction can only be made by the
    containment relation between the two bars, never by the close alone.

    See ``app.lakehouse.forming_bar`` for the containment relation.
    """
    if frame is None or frame.empty or "timestamp" not in frame.columns:
        return {}
    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working = working.dropna(subset=["timestamp"])
    if working.empty:
        return {}
    if symbol is not None and "symbol" not in working.columns:
        working["symbol"] = symbol
    try:
        working, _report = canonicalize_daily_sessions(working)
    except Exception:  # noqa: BLE001 - fall back to the raw rows
        pass
    if "close" not in working.columns:
        return {}
    working["_close"] = pd.to_numeric(working["close"], errors="coerce")
    working = working.dropna(subset=["_close"])
    if working.empty:
        return {}
    working = working.sort_values("timestamp")
    if "symbol" in working.columns:
        days = session_days(working)
    else:
        days = working["timestamp"].map(lambda stamp: session_day_of(stamp, symbol))
    working["_day"] = days

    bars: dict[str, dict] = {}
    for day, group in working.groupby("_day", sort=False):
        # The canonical row is the LAST one for the session: that is the
        # settled bar whenever both a snapshot and a settled bar are present.
        row = group.iloc[-1]
        bar = {"close": float(row["_close"])}
        for column in ("high", "low", "volume"):
            if column in row.index:
                value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
                bar[column] = None if pd.isna(value) else float(value)
            else:
                bar[column] = None
        bars[str(day)] = bar
    return bars


def _layer_closes(
    storage, layer: str, index: dict[str, list[str]], symbol: str, days: int
) -> dict[str, float]:
    """The closes of one symbol inside a trailing window, keyed by date.

    The partitions are selected from the PRE-BUILT INDEX, so this costs one
    or two object downloads per symbol instead of a paginated listing.
    """
    keys = _window_keys(index.get(symbol, []), days)
    if not keys:
        return {}
    frames: list[pd.DataFrame] = []
    for key in sorted(keys, reverse=True)[:3]:
        try:
            frame = storage.read_parquet(layer, key)
        except Exception:  # noqa: BLE001 - a missing partition is not fatal
            continue
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return {}
    combined = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
    return _session_closes(combined, symbol)


def _three_indexes(storage, indexes: dict | None) -> tuple[dict, dict, dict]:
    """The Bronze, Silver and Gold partition indexes.

    They are built once and shared by every check, because building them
    costs one paginated listing per layer and the checks all need the same
    three. The caller can pass a pre-built set so the whole pass pays for
    the listings once.
    """
    if indexes is not None and "bronze" in indexes:
        return indexes["bronze"], indexes["silver"], indexes["gold"]
    return (
        partition_index(storage, "bronze"),
        partition_index(storage, "silver"),
        partition_index(storage, "gold"),
    )


def check_layer_agreement(
    storage, symbols: list[str], days: int = 30, indexes: dict | None = None
) -> CheckResult:
    """Do Bronze, Silver and Gold hold the same close for the same session?

    WHY THIS CHECK EXISTS
    ---------------------
    This is the defect that no other check can see. A provider RESTATEMENT -
    the provider revising a bar it had already published - does not grow the
    Bronze partition, so the auto-refresh concluded "nothing new for this
    symbol" and never rebuilt Silver and Gold. Bronze then held the
    provider's current value while Silver and Gold held an older one, and
    the web served the older one FOREVER.

    Measured on 2026-11-03: 30 European symbols were in that state, with
    ADS.DE 2026-11-03 stored at 168.85 while the provider had revised it to
    168.10.

    A fresh re-fetch does not fix it either, because the fresh value goes
    into Bronze, and Bronze is not what Silver and Gold were built from.
    Only a FORCED REBUILD does. So the gate has to see it.
    """
    result = CheckResult()
    if not symbols:
        result.status = "unavailable"
        result.reason = "the lakehouse holds no symbols"
        return result

    bronze_index, silver_index, gold_index = _three_indexes(storage, indexes)

    def _one(symbol: str) -> tuple[str, bool, int, bool]:
        """Return (symbol, mismatched, shared_sessions, readable)."""
        try:
            bronze = _layer_closes(storage, "bronze", bronze_index, symbol, days)
            silver = _layer_closes(storage, "silver", silver_index, symbol, days)
            gold = _layer_closes(storage, "gold", gold_index, symbol, days)
        except Exception as exc:  # noqa: BLE001 - an unreadable symbol is a finding
            logger.debug("layer agreement read failed for %s: %s", symbol, exc)
            return symbol, False, 0, False

        if not bronze:
            return symbol, False, 0, True

        shared = 0
        for closes in (silver, gold):
            if not closes:
                continue
            for day, stored_close in closes.items():
                source_close = bronze.get(day)
                if source_close is None:
                    continue
                shared += 1
                diff = abs(stored_close - source_close)
                if diff / max(abs(source_close), 1e-9) > PRICE_TOLERANCE:
                    return symbol, True, shared, True
        return symbol, False, shared, True

    offenders: list[str] = []
    unreadable = 0
    compared_sessions = 0

    # The work is MinIO I/O, not computation, so it runs on a thread pool.
    # Measured on 2026-11-15: 100 symbols took 50s serially; the reads are
    # latency-bound, so overlapping them turns the pass from minutes into
    # well under one.
    with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
        futures = [pool.submit(_one, symbol) for symbol in symbols]
        for future in as_completed(futures):
            symbol, mismatched, shared, readable = future.result()
            if not readable:
                unreadable += 1
                continue
            compared_sessions += shared
            if mismatched:
                offenders.append(symbol)

    result.checked = len(symbols)
    result.failed = len(offenders)
    result.offenders = offenders[:50]
    result.details = {
        "compared_sessions": compared_sessions,
        "unreadable_symbols": unreadable,
        "window_days": days,
    }
    if unreadable and not offenders:
        result.status = "warning"
        result.warned = unreadable
        result.reason = f"{unreadable} symbol(s) could not be read"
    else:
        result.status = "failed" if offenders else "passed"
    return result


# ---------------------------------------------------------------------------
# Check 3: do the stored rows still obey the market's own rules?
# ---------------------------------------------------------------------------


def check_integrity(storage, symbols: list[str], indexes: dict | None = None) -> CheckResult:
    """Do the Silver rows satisfy the rules a real bar must satisfy?

    The rules are the market's own, not arbitrary thresholds:

    * ``low <= open <= high`` and ``low <= close <= high`` - a bar whose
      close is above its high is not a bar;
    * ``volume >= 0`` - a negative volume is not a volume;
    * one bar per session - the lakehouse is single-interval, so a second
      row for the same day is a defect, not extra information;
    * the series is monotonic in time.

    This is checked on SILVER, not on Bronze. Bronze holds whatever the
    provider published, including the raw ticks the plausibility screen
    let through; Silver is the layer the rest of the system reads, so it is
    the layer whose correctness matters.

    It reads only the NEWEST partition of each symbol. A defect in the
    recent bars is the one that reaches the charts and the forecasts; the
    full history is covered by the divergence scan, which is a separate,
    slower job.
    """
    result = CheckResult()
    if not symbols:
        result.status = "unavailable"
        result.reason = "the lakehouse holds no symbols"
        return result

    offenders: list[str] = []
    checked = 0
    unreadable = 0

    silver_index = (indexes or {}).get("silver")
    if silver_index is None:
        silver_index = partition_index(storage, "silver")

    def _one(symbol: str) -> tuple[bool, bool]:
        """Return (readable, violated)."""
        keys = silver_index.get(symbol, [])
        if not keys:
            return False, False
        try:
            frame = storage.read_parquet("silver", sorted(keys, reverse=True)[0])
        except Exception as exc:  # noqa: BLE001
            logger.debug("integrity read failed for %s: %s", symbol, exc)
            return False, False
        if frame is None or frame.empty:
            return False, False

        working = frame.copy()
        working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
        working = working.dropna(subset=["timestamp"])
        for column in ("open", "high", "low", "close", "volume"):
            if column in working.columns:
                working[column] = pd.to_numeric(working[column], errors="coerce")

        return True, bool(_integrity_reasons(working))

    with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
        futures = {pool.submit(_one, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            readable, violated = future.result()
            if not readable:
                unreadable += 1
                continue
            checked += 1
            if violated:
                offenders.append(symbol)

    result.checked = checked
    result.failed = len(offenders)
    result.offenders = offenders[:50]
    result.details = {"unreadable_symbols": unreadable}
    if unreadable and not offenders:
        result.status = "warning"
        result.warned = unreadable
        result.reason = f"{unreadable} symbol(s) could not be read"
    else:
        result.status = "failed" if offenders else "passed"
    return result


def _integrity_reasons(frame: pd.DataFrame) -> list[str]:
    """Which market rules this frame violates. Empty list = the frame is sane."""
    reasons: list[str] = []
    if frame.empty:
        return reasons

    for column in ("open", "high", "low", "close"):
        if column not in frame.columns:
            return ["missing_columns"]
        if frame[column].isna().any():
            reasons.append(f"missing_{column}")

    if "volume" in frame.columns and (frame["volume"].dropna() < 0).any():
        reasons.append("negative_volume")

    if not reasons:
        high = frame["high"]
        low = frame["low"]
        tolerance = 1e-9
        if not (
            (high >= frame["open"] - tolerance).all()
            and (high >= frame["close"] - tolerance).all()
            and (low <= frame["open"] + tolerance).all()
            and (low <= frame["close"] + tolerance).all()
        ):
            reasons.append("invalid_ohlc")

    if not frame["timestamp"].is_monotonic_increasing:
        reasons.append("non_monotonic_time")

    days = frame["timestamp"].dt.strftime("%Y-%m-%d")
    if days.duplicated().any():
        reasons.append("duplicate_session")

    return reasons


# ---------------------------------------------------------------------------
# Check 4: is each symbol current?
# ---------------------------------------------------------------------------


def check_freshness(storage, symbols: list[str], indexes: dict | None = None) -> CheckResult:
    """Does each symbol hold a bar for a recent session?

    A stale symbol is not WRONG, and saying it is would be dishonest. But it
    is not current either, and a stale symbol silently poisons everything
    computed over it: the forecast is trained on history that ended weeks
    ago, the indicators are computed on a series that never moves, and the
    chart shows a flat line that looks like a quiet market.

    The reference point is the NEWEST session ANY symbol in the universe
    holds - not the calendar date. The universe spans markets whose
    holidays never coincide, so a calendar-date comparison would flag most
    of it as stale on any given holiday Monday.
    """
    result = CheckResult()
    if not symbols:
        result.status = "unavailable"
        result.reason = "the lakehouse holds no symbols"
        return result

    newest_by_symbol: dict[str, str] = {}

    gold_index = (indexes or {}).get("gold")
    if gold_index is None:
        gold_index = partition_index(storage, "gold")

    def _one(symbol: str) -> str | None:
        """The symbol's newest session date, or None when it has none."""
        keys = gold_index.get(symbol, [])
        if not keys:
            return None
        try:
            frame = storage.read_parquet("gold", sorted(keys, reverse=True)[0])
        except Exception as exc:  # noqa: BLE001
            logger.debug("freshness read failed for %s: %s", symbol, exc)
            return None
        if frame is None or frame.empty or "timestamp" not in frame.columns:
            return None
        stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dropna()
        if stamps.empty:
            return None
        day = session_date(stamps.max(), symbol)
        return day.isoformat() if day else None

    with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
        futures = {pool.submit(_one, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            day = future.result()
            if day:
                newest_by_symbol[symbol] = day

    if not newest_by_symbol:
        result.status = "unavailable"
        result.reason = "no symbol holds a Gold bar"
        return result

    newest_session = max(newest_by_symbol.values())
    reference = datetime.fromisoformat(newest_session)
    stale: list[str] = []
    for symbol, day in newest_by_symbol.items():
        try:
            gap = (reference - datetime.fromisoformat(day)).days
        except ValueError:
            continue
        if gap > STALE_AFTER_DAYS:
            stale.append(symbol)

    result.checked = len(newest_by_symbol)
    result.warned = len(stale)
    result.offenders = sorted(stale)[:50]
    result.details = {
        "newest_session_in_lakehouse": newest_session,
        "stale_after_days": STALE_AFTER_DAYS,
        "stale_symbols": len(stale),
    }
    result.status = "warning" if stale else "passed"
    return result


# ---------------------------------------------------------------------------
# Check 5: do the providers agree with each other?
# ---------------------------------------------------------------------------


def check_source_agreement(storage, symbols: list[str], indexes: dict | None = None) -> CheckResult:
    """Do two providers that both served a symbol agree on its close?

    A symbol ingested from two providers - ``yahoo_http`` and ``vn_rest``,
    say - must produce the same session close from both. Otherwise the
    lakehouse holds two different "truths" for the same trading day, and
    which one reaches the chart depends on which row sorts last.

    This check is cheap because it reads what is already stored: the
    ``source`` column of the Bronze rows.

    WHY IT EXCLUDES EXPLAINED DISAGREEMENTS
    ---------------------------------------
    Two providers can disagree because one of them was captured MID-SESSION
    - a bar whose close is the last trade price of the moment the fetch
    ran, before the exchange closed. The measured case (15/11/2026): AMD
    2026-10-28 was written by ``yfinance_eod`` at 16:29 UTC, 3.5 hours
    before the NYSE close, with close=567.00, while ``yahoo_http`` had the
    settled close of 578.44. The provider confirmed 578.44 as the real
    close, so there was never a disagreement about the market - only a
    snapshot that was later superseded.

    Reporting that as a provider disagreement is a FALSE ALARM: it names
    the wrong cause, and it leaves the operator hunting for a provider bug
    that does not exist. So a session where the disagreement is fully
    explained by a mid-session snapshot is excluded from this check and
    reported by ``check_forming_snapshots`` instead, which names the real
    defect.

    A disagreement that is NOT explained by a snapshot still fails here -
    that is the case this check exists for.
    """
    result = CheckResult()
    if not symbols:
        result.status = "unavailable"
        result.reason = "the lakehouse holds no symbols"
        return result

    offenders: list[str] = []
    multi_source_symbols = 0
    compared_sessions = 0
    explained_sessions = 0

    bronze_index = (indexes or {}).get("bronze")
    if bronze_index is None:
        bronze_index = partition_index(storage, "bronze")

    def _one(symbol: str) -> tuple[bool, int, int, int]:
        """Return (disagrees, shared_sessions, has_multiple_sources, explained)."""
        keys = _window_keys(bronze_index.get(symbol, []), 60)
        if not keys:
            return False, 0, 0, 0
        frames: list[pd.DataFrame] = []
        for key in sorted(keys, reverse=True)[:3]:
            try:
                frame = storage.read_parquet("bronze", key)
            except Exception:  # noqa: BLE001
                continue
            if frame is not None and not frame.empty:
                frames.append(frame)
        if not frames:
            return False, 0, 0, 0
        frame = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
        if "source" not in frame.columns:
            return False, 0, 0, 0
        working = frame.copy()
        working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
        working = working.dropna(subset=["timestamp"])
        sources = [s for s in working["source"].dropna().unique() if str(s).strip()]
        if len(sources) < 2:
            return False, 0, 0, 0

        # The trading day of a row, in its EXCHANGE's local calendar. Two
        # providers stamp the same session at different hours of the same
        # UTC day for every market, but for the exchanges whose session
        # crosses UTC midnight (``.AX``) the two stamps can even fall on
        # different UTC days - see ``app.lakehouse.exchange_timezone``.
        working["_day"] = session_days(working).astype(str)
        working["_close"] = pd.to_numeric(working["close"], errors="coerce")
        pivot = working.pivot_table(
            index="_day", columns="source", values="_close", aggfunc="last"
        )
        shared = 0
        explained = 0
        for column in sources[1:]:
            if column not in pivot.columns:
                continue
            both = pivot[[sources[0], column]].dropna()
            if both.empty:
                continue
            shared += len(both)
            relative = (
                (both[sources[0]] - both[column]).abs()
                / both[column].abs().clip(lower=1e-9)
            )
            disagreeing_days = [
                day for day, gap in relative.items() if gap > 0.01
            ]
            if not disagreeing_days:
                continue
            # The sources disagree on at least one session. If EVERY
            # disagreeing session is explained by a mid-session snapshot,
            # the disagreement is not a provider conflict.
            unexplained = _unexplained_disagreements(
                working, sources[0], column, disagreeing_days
            )
            if unexplained == 0:
                explained += len(disagreeing_days)
                continue
            return True, shared, 1, explained
        return False, shared, 1, explained

    with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
        futures = {pool.submit(_one, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            disagrees, shared, multi, explained = future.result()
            compared_sessions += shared
            multi_source_symbols += multi
            explained_sessions += explained
            if disagrees:
                offenders.append(symbol)

    result.checked = len(symbols)
    result.failed = len(offenders)
    result.offenders = offenders[:50]
    result.details = {
        "multi_source_symbols": multi_source_symbols,
        "compared_sessions": compared_sessions,
        "explained_by_mid_session_snapshot": explained_sessions,
        "tolerance": 0.01,
    }
    result.status = "failed" if offenders else "passed"
    return result


def _unexplained_disagreements(
    working: pd.DataFrame,
    first_source: str,
    second_source: str,
    days: Iterable,
) -> int:
    """How many of these sessions disagree for a reason OTHER than a snapshot.

    A session where the two sources' rows form a mid-session/settled pair
    is explained: one of them was captured before the exchange closed, and
    the settled bar supersedes it. See
    ``app.lakehouse.forming_bar``.
    """
    day_list = list(days)
    if not day_list:
        return 0

    unexplained = 0
    for day in day_list:
        group = working[working["_day"] == day]
        rows = group[group["source"].isin([first_source, second_source])]
        if len(rows) < 2:
            continue
        if find_forming_snapshots(rows):
            # Explained: one of the two rows is a frozen mid-session bar.
            continue
        unexplained += 1
    return unexplained


# ---------------------------------------------------------------------------
# Check 5b: does Bronze hold a bar that was frozen mid-session?
# ---------------------------------------------------------------------------


def check_forming_snapshots(storage, symbols: list[str], indexes: dict | None = None) -> CheckResult:
    """Does Bronze hold a daily bar that was captured while its session ran?

    WHY THIS IS A SEPARATE CHECK
    ----------------------------
    ``check_source_agreement`` above asks whether two providers agree on a
    close. It cannot tell WHY they disagree, so a mid-session snapshot -
    a bar whose close is the last trade price of the moment the fetch ran,
    captured before the exchange closed - is reported as a provider
    disagreement, which is the wrong explanation.

    The measured case (15/11/2026): AMD 2026-10-28 was written by
    ``yfinance_eod`` at 16:29 UTC, 3.5 hours before the NYSE close, with
    close=567.00 and volume=7,367,032. The provider's settled close was
    578.44 with volume 18,848,600. The gate failed on AMD and INTC, and
    the reason looked like two providers lying about the same session.

    WHAT THIS CHECK ACCOMPLISHES
    ----------------------------
    It names the defect. A session's high and low can only expand as the
    session runs and its volume can only grow, so the settled bar always
    CONTAINS the forming one - see ``app.lakehouse.forming_bar``. That
    relation identifies the stale row without a calendar of market hours,
    so it works for every market in the universe.

    WHAT IT DELIBERATELY DOES NOT DO
    --------------------------------
    It does not delete anything. Bronze is the RAW layer: it records what
    the provider actually said, and it is allowed to hold a snapshot that
    was later superseded by the settled bar. Silver and Gold already pick
    the settled row (they prefer the canonical session stamp), so the
    product is correct; the defect is that the RAW layer keeps a row that
    will read as a contradiction to every future audit.

    So this check is a WARNING, not a failure: it says "the raw layer
    holds N frozen snapshots", which is a fact worth knowing and not a
    defect that corrupts what the web serves.
    """
    result = CheckResult()
    if not symbols:
        result.status = "unavailable"
        result.reason = "the lakehouse holds no symbols"
        return result

    offenders: list[str] = []
    sessions = 0

    bronze_index = (indexes or {}).get("bronze")
    if bronze_index is None:
        bronze_index = partition_index(storage, "bronze")

    def _one(symbol: str) -> tuple[int, list[str]]:
        """Return (snapshot_count, affected_session_labels)."""
        keys = _window_keys(bronze_index.get(symbol, []), 60)
        if not keys:
            return 0, []
        frames: list[pd.DataFrame] = []
        for key in sorted(keys, reverse=True)[:3]:
            try:
                frame = storage.read_parquet("bronze", key)
            except Exception:  # noqa: BLE001
                continue
            if frame is not None and not frame.empty:
                frames.append(frame)
        if not frames:
            return 0, []
        frame = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
        if "timestamp" not in frame.columns:
            return 0, []

        working = frame.copy()
        working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
        working = working.dropna(subset=["timestamp"])
        if working.empty:
            return 0, []

        working["_day"] = session_days(working).astype(str)
        count = 0
        labels: list[str] = []
        for (day,), group in working.groupby(["_day"], sort=False):
            if len(group) < 2:
                continue
            pairs = find_forming_snapshots(group)
            if not pairs:
                continue
            count += len(pairs)
            labels.append(f"{day}:{len(pairs)}")
        return count, labels

    with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
        futures = {pool.submit(_one, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                count, labels = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.debug("forming-snapshot check failed for %s: %s", symbol, exc)
                continue
            if count:
                sessions += count
                offenders.append(f"{symbol} ({', '.join(labels[:3])})")

    result.checked = len(symbols)
    result.warned = len(offenders)
    result.offenders = offenders[:50]
    result.details = {
        "frozen_sessions": sessions,
        "symbols_with_frozen_sessions": len(offenders),
    }
    result.status = "warning" if offenders else "passed"
    return result


def _next_batch(symbols: list[str], rotation: dict, batch_size: int) -> list[str]:
    """The next slice of the universe for the provider comparison.

    The rotation is a CURSOR over the symbol list, persisted between
    passes. Each pass takes the next ``batch_size`` symbols and moves the
    cursor on, so a full sweep of the universe completes every
    ``len(symbols) / batch_size`` passes and no symbol is checked twice
    before the sweep ends.

    The cursor is stored by INDEX rather than by symbol, so a symbol that
    is removed from the universe does not break the rotation.
    """
    if not symbols:
        return []
    start = int(rotation.get("cursor", 0)) % len(symbols)
    size = min(batch_size, len(symbols))
    batch = [symbols[(start + offset) % len(symbols)] for offset in range(size)]
    rotation["cursor"] = (start + size) % len(symbols)
    return batch


def check_against_provider(
    symbols: list[str],
    batch_size: int = PROVIDER_CHECK_BATCH,
    window: int = PROVIDER_CHECK_WINDOW,
    provider_name: str = "yahoo_http",
    storage=None,
    indexes: dict | None = None,
) -> tuple[CheckResult, list[str]]:
    """Compare a slice of the universe against the live provider.

    This is the only check that is INDEPENDENT of the lakehouse: it asks
    the provider what the price was, and compares. Everything else compares
    the lakehouse against itself, and a lakehouse that is consistently wrong
    is consistently wrong in all of them.

    It runs on a ROTATION because it is the only check that costs a network
    call per symbol. See ``_next_batch``.

    A provider that cannot be reached makes the check ``unavailable``, not
    ``passed``. A gate that reports "clean" because the network was down is
    exactly the failure mode this project is not allowed to have.
    """
    result = CheckResult()
    try:
        from app.data_sources.factory import get_data_provider

        provider = get_data_provider(provider_name)
    except Exception as exc:  # noqa: BLE001
        result.status = "unavailable"
        result.reason = f"provider {provider_name!r} unavailable: {exc}"
        return result, []

    exact = 0
    tolerant = 0
    stale = 0
    mismatches: list[str] = []
    errors: list[str] = []

    if storage is None:
        from app.lakehouse.storage_factory import get_storage_backend

        storage = get_storage_backend()

    def _one(symbol: str) -> tuple[str, dict[str, int]]:
        """Compare every shared session of one symbol, and tally the verdicts."""
        tally = {"EXACT": 0, "TOLERANT": 0, "STALE": 0, "MISMATCH": 0}
        try:
            frame = provider.get_historical_data(symbol, interval="1d")
        except Exception:  # noqa: BLE001
            return symbol, {"ERROR": 1}
        if frame is None or frame.empty or "timestamp" not in frame.columns:
            return symbol, tally
        live = frame.copy()
        live["timestamp"] = pd.to_datetime(live["timestamp"], utc=True, errors="coerce")
        live = live.dropna(subset=["timestamp"])
        if "symbol" not in live.columns:
            live["symbol"] = symbol
        if live.empty:
            return symbol, tally
        live["_close"] = pd.to_numeric(live["close"], errors="coerce")
        live = live.dropna(subset=["_close"])
        # The session day is derived in the EXCHANGE's timezone, for the same
        # reason the stored side is: the ASX's 23:00Z bar belongs to the NEXT
        # local session, so keying it by the UTC date would make the two sides
        # disagree about which close belongs to which day.
        live["_day"] = session_days(live).astype(str)
        # The WHOLE provider bar is kept, not just its close: a mid-session
        # snapshot can only be recognised by comparing the two bars' ranges
        # and volumes against each other. See ``app.lakehouse.forming_bar``.
        live_bars: dict[str, dict] = {}
        for day, group in live.groupby("_day", sort=False):
            row = group.iloc[-1]
            bar = {"close": float(row["_close"])}
            for column in ("high", "low", "volume"):
                if column in row.index:
                    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
                    bar[column] = None if pd.isna(value) else float(value)
                else:
                    bar[column] = None
            live_bars[str(day)] = bar
        live = live.groupby("_day", as_index=False)["_close"].last().set_index("_day")

        stored = _stored_bars(symbol, storage, window, indexes)
        if not stored:
            return symbol, tally

        sessions = sorted(set(stored) & set(live.index))[-window:]
        for day in sessions:
            stored_bar = stored[day]
            stored_close = stored_bar["close"]
            provider_close = float(live.loc[day, "_close"])
            diff = abs(stored_close - provider_close)
            if diff == 0.0:
                tally["EXACT"] += 1
                continue
            if diff / max(abs(provider_close), 1e-9) <= PRICE_TOLERANCE:
                tally["TOLERANT"] += 1
                continue
            # A MID-SESSION SNAPSHOT is not a disagreement. The stored bar was
            # captured while its own session was still open, so its close is
            # the last trade price of that moment; the provider's close is
            # the settled one. The containment relation identifies this
            # without a market-hours calendar: the settled bar's range
            # contains the snapshot's range and its volume is larger.
            #
            # Reporting it as a mismatch names the WRONG cause and sends the
            # operator hunting for a provider bug that does not exist - the
            # same false alarm ``check_source_agreement`` already avoids by
            # excluding explained sessions.
            provider_bar = live_bars.get(day)
            if provider_bar is not None and _is_forming_snapshot(stored_bar, provider_bar):
                tally["STALE"] += 1
                continue
            # A difference this large is either a real mismatch or the
            # provider having revised its own history. The two are told
            # apart the same way the verifier tells them apart: a stored
            # close that matches the provider's value for a DIFFERENT
            # session is a timestamp shift, and a difference under 1% on a
            # settled session is a provider-side restatement. Neither is a
            # lakehouse defect, so neither is reported as one.
            provider_closes = live["_close"].dropna()
            if not provider_closes.empty:
                nearest = (provider_closes - stored_close).abs().idxmin()
                if abs(provider_closes.loc[nearest] - stored_close) / max(stored_close, 1e-9) <= PRICE_TOLERANCE:
                    tally["STALE"] += 1
                    continue
            if diff / max(abs(provider_close), 1e-9) <= 0.01:
                tally["STALE"] += 1
                continue
            tally["MISMATCH"] += 1
        return symbol, tally

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_one, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                _, tally = future.result()
            except Exception:  # noqa: BLE001
                tally = {"ERROR": 1}
            if tally.get("ERROR"):
                errors.append(symbol)
            exact += tally.get("EXACT", 0)
            tolerant += tally.get("TOLERANT", 0)
            stale += tally.get("STALE", 0)
            if tally.get("MISMATCH", 0):
                mismatches.append(symbol)

    result.checked = exact + tolerant + stale + len(mismatches)
    result.failed = len(mismatches)
    result.warned = len(errors)
    result.offenders = sorted(mismatches)[:50]
    result.details = {
        "provider": provider_name,
        "exact_sessions": exact,
        "tolerant_sessions": tolerant,
        "stale_sessions": stale,
        "provider_errors": len(errors),
        "window_sessions": window,
    }
    if errors and not mismatches:
        result.status = "warning"
        result.reason = f"{len(errors)} symbol(s) could not be checked against the provider"
    elif mismatches:
        result.status = "failed"
        result.reason = (
            f"{len(mismatches)} symbol(s) disagree with the provider on a SETTLED session"
        )
    else:
        result.status = "passed"
        if stale:
            # The comparison passed, but some sessions were explained by a
            # mid-session snapshot. That is a fact about the RAW layer worth
            # reporting, and it is already reported in detail by
            # ``check_forming_snapshots``.
            result.status = "warning"
            result.reason = (
                f"{stale} session(s) held a mid-session snapshot; "
                "no settled session disagrees with the provider"
            )
    return result, symbols


def _stored_closes(
    symbol: str,
    storage=None,
    days: int = PROVIDER_CHECK_WINDOW,
    indexes: dict | None = None,
) -> dict[str, float]:
    """The stored Silver closes of one symbol, keyed by session date.

    Only the trailing ``days`` are read. The provider comparison covers the
    same window, so reading more would be wasted I/O.
    """
    if storage is None:
        from app.lakehouse.storage_factory import get_storage_backend

        storage = get_storage_backend()
    silver_index = (indexes or {}).get("silver")
    if silver_index is None:
        silver_index = partition_index(storage, "silver")
    try:
        return _layer_closes(storage, "silver", silver_index, symbol, days)
    except Exception:  # noqa: BLE001
        return {}


def _is_forming_snapshot(stored_bar: dict, provider_bar: dict) -> bool:
    """Is the stored bar a mid-session snapshot of the provider's bar?

    The two bars describe the SAME session, so the range relation applies:
    their ranges must overlap and the settled bar trades more volume. The
    stored bar is the forming one when the provider's bar overlaps it AND
    trades more volume.

    This is the same test :mod:`app.lakehouse.forming_bar` applies to two
    rows of the same session inside Bronze - reused here for the one stored
    row against the one live provider row.

    Args:
        stored_bar: the stored bar, with ``close``/``high``/``low``/``volume``.
        provider_bar: the provider's bar, same keys.

    Returns:
        True when the stored bar looks like a frozen mid-session snapshot.
    """
    try:
        forming = pd.Series(
            {
                "close": stored_bar.get("close"),
                "high": stored_bar.get("high"),
                "low": stored_bar.get("low"),
                "volume": stored_bar.get("volume"),
            }
        )
        settled = pd.Series(
            {
                "close": provider_bar.get("close"),
                "high": provider_bar.get("high"),
                "low": provider_bar.get("low"),
                "volume": provider_bar.get("volume"),
            }
        )
    except Exception:  # noqa: BLE001 - a malformed bar is not a snapshot
        return False
    try:
        return forming_snapshot_reason(forming, settled)
    except Exception:  # noqa: BLE001
        return False


def _stored_bars(
    symbol: str,
    storage=None,
    days: int = PROVIDER_CHECK_WINDOW,
    indexes: dict | None = None,
) -> dict[str, dict]:
    """The stored Silver bars of one symbol, keyed by session date.

    The counterpart of :func:`_stored_closes` for the provider comparison:
    it keeps ``high``, ``low`` and ``volume`` so that a mid-session snapshot
    can be told apart from a real disagreement.
    """
    if storage is None:
        from app.lakehouse.storage_factory import get_storage_backend

        storage = get_storage_backend()
    silver_index = (indexes or {}).get("silver")
    if silver_index is None:
        silver_index = partition_index(storage, "silver")
    try:
        keys = _window_keys(silver_index.get(symbol, []), days)
    except Exception:  # noqa: BLE001
        return {}
    if not keys:
        return {}
    frames: list[pd.DataFrame] = []
    for key in sorted(keys, reverse=True)[:3]:
        try:
            frame = storage.read_parquet("silver", key)
        except Exception:  # noqa: BLE001 - a missing partition is not fatal
            continue
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return {}
    combined = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
    return _session_bars(combined, symbol)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def run_gate(
    symbols: list[str] | None = None,
    provider_batch: int = PROVIDER_CHECK_BATCH,
    provider_window: int = PROVIDER_CHECK_WINDOW,
    provider_name: str = "yahoo_http",
    rotation: dict | None = None,
    storage=None,
) -> QualityGateReport:
    """Run every check and produce the gate's verdict.

    ``rotation`` is the CURSOR state of the provider comparison. It is
    passed in and mutated in place, so the caller can persist it between
    passes and the full sweep completes over several passes.
    """
    started = datetime.now(UTC)
    if storage is None:
        from app.lakehouse.storage_factory import get_storage_backend

        storage = get_storage_backend()

    # The partition indexes are built ONCE and shared by every check.
    # Building them per check would mean one paginated listing per layer
    # per check - 12 listings instead of 3 - and the pass would spend most
    # of its time walking the same bucket keys.
    #
    # The symbol list comes from the Bronze index rather than from a
    # separate listing, because that listing would walk the same 100,000+
    # keys a second time.
    indexes: dict[str, dict[str, list[str]]] = {}
    try:
        indexes = {
            "bronze": partition_index(storage, "bronze"),
            "silver": partition_index(storage, "silver"),
            "gold": partition_index(storage, "gold"),
        }
    except Exception as exc:  # noqa: BLE001 - the checks will report it
        logger.warning("Quality gate could not build the partition indexes: %s", exc)

    if symbols is None:
        symbols = sorted(indexes.get("bronze", {}).keys())
        if not symbols:
            try:
                symbols = lakehouse_symbols(storage)
            except Exception as exc:  # noqa: BLE001
                report = QualityGateReport(checked_at=started)
                report.verdict = "failed"
                report.checks["storage"] = CheckResult(
                    status="unavailable", reason=f"the lakehouse could not be listed: {exc}"
                )
                return report

    # A symbol that looks like a test fixture must never be reported as
    # checked market data. The denylist is the same one the write path
    # uses, so the gate and the ledger agree on what a ticker is.
    symbols = [s for s in symbols if not is_fabricated_symbol(s)]

    rotation = rotation if rotation is not None else {}
    report = QualityGateReport(checked_at=started)

    report.checks["plausibility"] = check_plausibility(storage)
    report.checks["layer_agreement"] = check_layer_agreement(storage, symbols, indexes=indexes)
    report.checks["integrity"] = check_integrity(storage, symbols, indexes=indexes)
    report.checks["freshness"] = check_freshness(storage, symbols, indexes=indexes)
    report.checks["source_agreement"] = check_source_agreement(storage, symbols, indexes=indexes)
    report.checks["forming_snapshots"] = check_forming_snapshots(storage, symbols, indexes=indexes)

    batch = _next_batch(symbols, rotation, provider_batch)
    if batch:
        provider_result, batch = check_against_provider(
            batch,
            batch_size=provider_batch,
            window=provider_window,
            provider_name=provider_name,
            storage=storage,
            indexes=indexes,
        )
        report.checks["provider_agreement"] = provider_result
        report.provider_batch = batch
    else:
        report.checks["provider_agreement"] = CheckResult(
            status="unavailable", reason="the lakehouse holds no symbols"
        )

    report.verdict = _worst(check.status for check in report.checks.values())
    report.elapsed_seconds = (datetime.now(UTC) - started).total_seconds()
    logger.info(
        "Data quality gate: verdict=%s checked=%s symbol(s) in %.1fs",
        report.verdict,
        len(symbols),
        report.elapsed_seconds,
    )
    return report
