"""The source-agreement check must not blame a provider for a frozen snapshot.

WHY THIS TEST EXISTS
--------------------
On 15/11/2026 the quality gate failed on ``AMD`` and ``INTC`` under
``check_source_agreement``: two providers appeared to report different
closes for 2026-10-28.

    AMD 2026-10-28  yfinance_eod  close 567.00  vol  7,367,032
                    yahoo_http    close 578.44  vol 18,848,600

The provider confirmed 578.44 as the real settled close. The
``yfinance_eod`` row was written at 16:29 UTC - 3.5 hours before the NYSE
close - so it is a MID-SESSION SNAPSHOT, not a conflicting opinion. There
was never a disagreement about the market.

Reporting that as a provider conflict names the wrong cause and sends the
operator hunting for a provider bug that does not exist. So a session
whose disagreement is fully explained by a snapshot is excluded from
``check_source_agreement`` and reported by ``check_forming_snapshots``,
which names the real defect.

A disagreement that is NOT explained by a snapshot must still FAIL.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.quality_gate import (  # noqa: E402
    check_forming_snapshots,
    check_source_agreement,
)
from app.lakehouse.local_storage import LocalStorageBackend  # noqa: E402


def _row(
    symbol: str,
    stamp: str,
    source: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> dict:
    return {
        "symbol": symbol,
        "timestamp": pd.Timestamp(stamp, tz="UTC"),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "source": source,
        "ingestion_time": pd.Timestamp(stamp, tz="UTC"),
    }


def _write(storage: LocalStorageBackend, symbol: str, rows: list[dict]) -> None:
    frame = pd.DataFrame(rows)
    storage.write_parquet(
        "bronze",
        f"symbol={symbol}/year=2026/month=10/part-001.parquet",
        frame,
    )


@pytest.fixture()
def storage(tmp_path) -> LocalStorageBackend:
    return LocalStorageBackend(root=tmp_path)


# ── The measured AMD case ──────────────────────────────────────────────────


def test_a_mid_session_snapshot_is_not_reported_as_a_provider_conflict(
    storage: LocalStorageBackend,
) -> None:
    """AMD 2026-10-28: the two rows are a snapshot and its settled bar."""
    _write(
        storage,
        "AMD",
        [
            _row("AMD", "2026-10-28 04:00:00", "yfinance_eod",
                 572.52, 573.96, 560.52, 567.00, 7_367_032),
            _row("AMD", "2026-10-28 13:30:00", "yahoo_http",
                 573.08, 579.18, 560.52, 578.44, 18_848_600),
        ],
    )

    result = check_source_agreement(storage, ["AMD"])

    assert result.status != "failed"
    assert "AMD" not in result.offenders


def test_the_snapshot_is_reported_by_its_own_check(
    storage: LocalStorageBackend,
) -> None:
    """The defect must be NAMED, not hidden by excluding it."""
    _write(
        storage,
        "AMD",
        [
            _row("AMD", "2026-10-28 04:00:00", "yfinance_eod",
                 572.52, 573.96, 560.52, 567.00, 7_367_032),
            _row("AMD", "2026-10-28 13:30:00", "yahoo_http",
                 573.08, 579.18, 560.52, 578.44, 18_848_600),
        ],
    )

    result = check_forming_snapshots(storage, ["AMD"])

    assert result.status == "warning"
    assert result.warned == 1
    assert result.details["frozen_sessions"] == 1


# ── A real conflict must still fail ───────────────────────────────────────


def test_a_real_provider_conflict_still_fails(
    storage: LocalStorageBackend,
) -> None:
    """Two providers that disagree on a price with no snapshot explanation."""
    _write(
        storage,
        "MSFT",
        [
            _row("MSFT", "2026-10-28 13:30:00", "yahoo_http",
                 500.0, 510.0, 495.0, 505.00, 1_000_000),
            _row("MSFT", "2026-10-28 13:30:00", "web_scraper",
                 450.0, 460.0, 445.0, 455.00, 900_000),
        ],
    )

    result = check_source_agreement(storage, ["MSFT"])

    assert result.status == "failed"
    assert "MSFT" in result.offenders


def test_a_split_inside_the_session_is_still_a_conflict(
    storage: LocalStorageBackend,
) -> None:
    """A 50:1 split is a scale break, not a frozen snapshot."""
    _write(
        storage,
        "CMG",
        [
            _row("CMG", "2026-10-28 13:30:00", "yahoo_http",
                 19_900.0, 20_000.0, 19_500.0, 19_750.00, 100_000),
            _row("CMG", "2026-10-28 13:30:00", "web_scraper",
                 27.0, 28.0, 27.0, 27.52, 400_000),
        ],
    )

    result = check_source_agreement(storage, ["CMG"])

    assert result.status == "failed"
    assert "CMG" in result.offenders


# ── The bookkeeping ───────────────────────────────────────────────────────


def test_two_sources_that_agree_pass(
    storage: LocalStorageBackend,
) -> None:
    """The normal case: two providers reporting the same bar."""
    _write(
        storage,
        "AAPL",
        [
            _row("AAPL", "2026-10-28 04:00:00", "yfinance_eod",
                 349.11, 351.73, 345.75, 347.73, 39_539_700),
            _row("AAPL", "2026-10-28 13:30:00", "yahoo_http",
                 349.11, 351.73, 345.75, 347.73, 39_539_700),
        ],
    )

    result = check_source_agreement(storage, ["AAPL"])

    assert result.status == "passed"
    assert result.failed == 0


def test_a_symbol_with_one_source_is_not_a_conflict(
    storage: LocalStorageBackend,
) -> None:
    """A single provider cannot disagree with itself."""
    _write(
        storage,
        "NVDA",
        [_row("NVDA", "2026-10-28 13:30:00", "yahoo_http",
              180.0, 185.0, 178.0, 183.00, 5_000_000)],
    )

    result = check_source_agreement(storage, ["NVDA"])

    assert result.status == "passed"


def test_the_forming_snapshot_check_passes_when_there_is_none(
    storage: LocalStorageBackend,
) -> None:
    """A clean lakehouse must not be warned about."""
    _write(
        storage,
        "AAPL",
        [_row("AAPL", "2026-10-28 13:30:00", "yahoo_http",
              349.11, 351.73, 345.75, 347.73, 39_539_700)],
    )

    result = check_forming_snapshots(storage, ["AAPL"])

    assert result.status == "passed"
    assert result.warned == 0


def test_an_empty_lakehouse_reports_unavailable() -> None:
    """A check that could not run must never report a pass."""
    for check in (check_source_agreement, check_forming_snapshots):
        result = check(None, [])
        assert result.status == "unavailable"
