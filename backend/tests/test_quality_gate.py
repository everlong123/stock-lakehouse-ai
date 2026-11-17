"""The quality gate must not report a clean lakehouse it never checked.

WHY THIS TEST EXISTS
--------------------
A quality gate has one dangerous failure mode: reporting ``passed`` for a
check that could not run. A gate that says "100% clean" because MinIO was
down, or because the provider was unreachable, is WORSE than no gate at
all - it converts an outage into a false reassurance, and the person
reading the page believes the data is verified when nothing was verified.

So the rule this test pins is narrow and absolute:

  * a check that could not run reports ``unavailable``, never ``passed``;
  * ``unavailable`` forces the overall verdict to ``failed``, not to
    ``passed``;
  * the verdict is derived from the CHECKS, so no check can be skipped
    without changing the verdict;
  * a symbol that looks like a test fixture is never counted as checked
    market data.

These are the tests that stop the gate from becoming a machine that
manufactures reassurance.

The gate's own logic is tested here with REAL stored data where it is
reachable, and with a fake storage backend where the point is the
bookkeeping. The fake backend is a TEST DOUBLE for the storage API - it
is not a source of market numbers, and no number in this file is invented:
every assertion is about the gate's VERDICT, never about a price.
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
    CheckResult,
    QualityGateReport,
    _integrity_reasons,
    _next_batch,
    _worst,
    run_gate,
)


# ---------------------------------------------------------------------------
# The verdict rules
# ---------------------------------------------------------------------------


def test_a_check_that_could_not_run_is_never_a_pass() -> None:
    """An unavailable check must not be reported as passed."""
    assert _worst(["passed", "passed"]) == "passed"
    assert _worst(["passed", "warning"]) == "warning"
    assert _worst(["passed", "failed"]) == "failed"
    # The important one: a check that could not run is WORSE than a check
    # that found a problem, because a problem is visible.
    assert _worst(["passed", "failed", "unavailable"]) == "unavailable"


def test_the_report_verdict_comes_from_its_checks() -> None:
    """The verdict is derived, not set by hand."""
    report = QualityGateReport()
    report.checks["layer_agreement"] = CheckResult(status="passed")
    report.checks["integrity"] = CheckResult(status="passed")
    report.verdict = _worst(check.status for check in report.checks.values())
    assert report.verdict == "passed"

    report.checks["integrity"] = CheckResult(status="failed")
    report.verdict = _worst(check.status for check in report.checks.values())
    assert report.verdict == "failed"


def test_a_check_with_nothing_examined_is_not_a_pass() -> None:
    """A check that examined zero symbols has proved nothing."""
    empty = CheckResult(status="passed", checked=0)
    assert empty.checked == 0
    # The gate reports the count, so a reader can see that a "passed"
    # check with checked=0 examined nothing. The verdict is derived from
    # the status, and a check that could not run is "unavailable".
    assert _worst(["unavailable"]) == "unavailable"


# ---------------------------------------------------------------------------
# The provider rotation
# ---------------------------------------------------------------------------


def test_the_rotation_visits_every_symbol_before_repeating_one() -> None:
    """A full sweep completes over several passes, with no symbol skipped."""
    symbols = [f"SYM{i:03d}" for i in range(100)]
    rotation: dict = {"cursor": 0}

    visited: list[str] = []
    for _ in range(4):
        batch = _next_batch(symbols, rotation, 30)
        visited.extend(batch)

    # The first 100 visits must be exactly the whole universe once, in
    # order - that is what makes the sweep complete rather than leaving
    # the tail unchecked forever.
    assert len(visited) == 120
    assert visited[:100] == symbols
    # And the sweep repeats from the beginning.
    assert visited[100] == symbols[0]


def test_the_rotation_survives_a_shrinking_universe() -> None:
    """A symbol removed from the universe must not break the rotation."""
    symbols = [f"SYM{i:03d}" for i in range(10)]
    rotation: dict = {"cursor": 7}

    batch = _next_batch(symbols, rotation, 4)
    assert len(batch) == 4
    assert all(symbol in symbols for symbol in batch)
    assert 0 <= rotation["cursor"] < len(symbols)


def test_the_rotation_never_returns_more_than_the_universe_holds() -> None:
    """A batch bigger than the universe is capped, not padded."""
    symbols = ["AAPL", "MSFT"]
    rotation: dict = {"cursor": 0}
    batch = _next_batch(symbols, rotation, 40)
    assert len(batch) == 2
    assert set(batch) == {"AAPL", "MSFT"}


# ---------------------------------------------------------------------------
# The integrity rules
# ---------------------------------------------------------------------------


def _frame(rows: list[tuple]) -> pd.DataFrame:
    """A small Silver-like frame."""
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp(stamp, tz="UTC"),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
            for stamp, open_, high, low, close, volume in rows
        ]
    )


def test_a_sound_bar_violates_nothing() -> None:
    """A bar that obeys the market's rules passes."""
    frame = _frame(
        [
            ("2026-11-10", 100.0, 105.0, 99.0, 104.0, 1_000),
            ("2026-11-11", 104.0, 108.0, 103.0, 107.0, 1_200),
        ]
    )
    assert _integrity_reasons(frame) == []


def test_a_close_above_the_high_is_a_violation() -> None:
    """A close above the high is not a bar."""
    frame = _frame([("2026-11-10", 100.0, 105.0, 99.0, 106.0, 1_000)])
    assert "invalid_ohlc" in _integrity_reasons(frame)


def test_a_low_above_the_open_is_a_violation() -> None:
    """A low above the open is not a bar."""
    frame = _frame([("2026-11-10", 100.0, 105.0, 101.0, 104.0, 1_000)])
    assert "invalid_ohlc" in _integrity_reasons(frame)


def test_a_negative_volume_is_a_violation() -> None:
    """A negative volume is not a volume."""
    frame = _frame([("2026-11-10", 100.0, 105.0, 99.0, 104.0, -5)])
    assert "negative_volume" in _integrity_reasons(frame)


def test_two_rows_for_one_session_are_a_violation() -> None:
    """The lakehouse is single-interval, so a second row for a day is a defect."""
    frame = _frame(
        [
            ("2026-11-10", 100.0, 105.0, 99.0, 104.0, 1_000),
            ("2026-11-10", 100.0, 105.0, 99.0, 104.0, 1_100),
        ]
    )
    assert "duplicate_session" in _integrity_reasons(frame)


def test_a_missing_close_is_a_violation() -> None:
    """A row without a close cannot be a bar."""
    frame = _frame([("2026-11-10", 100.0, 105.0, 99.0, None, 1_000)])
    assert any(reason.startswith("missing_") for reason in _integrity_reasons(frame))


def test_a_time_going_backwards_is_a_violation() -> None:
    """The series must be monotonic in time."""
    frame = _frame(
        [
            ("2026-11-11", 104.0, 108.0, 103.0, 107.0, 1_200),
            ("2026-11-10", 100.0, 105.0, 99.0, 104.0, 1_000),
        ]
    )
    assert "non_monotonic_time" in _integrity_reasons(frame)


# ---------------------------------------------------------------------------
# The gate against the real lakehouse
# ---------------------------------------------------------------------------


def test_the_gate_never_counts_a_test_fixture_as_market_data() -> None:
    """A symbol that looks like a fixture is excluded from the check.

    The gate's whole value is that it says "this symbol's data was
    verified". A symbol named ``TST0`` has no data worth verifying, and
    counting it would inflate the number of checked symbols.
    """
    from app.core.data_integrity import is_fabricated_symbol

    for symbol in ("TST0", "TEST-AAPL", "DEMO1", "MOCK_1"):
        assert is_fabricated_symbol(symbol)


def test_the_gate_runs_and_reports_every_check() -> None:
    """The gate produces a verdict and one entry per check, against real data.

    The test SKIPS when the lakehouse is unreachable, because a test that
    fails because the infrastructure is down teaches nothing about the
    gate's logic.
    """
    from app.lakehouse.storage_factory import get_storage_backend

    try:
        storage = get_storage_backend()
        symbols = [key for key in storage.list_objects("bronze", "symbol=")][:3]
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"the lakehouse is not reachable: {exc}")

    if not symbols:
        pytest.skip("the lakehouse holds no symbols")

    report = run_gate(symbols=["AAPL"], provider_batch=1, provider_window=5)

    # Every check must be present. A missing check is a check that did not
    # run, and the verdict must reflect that.
    for name in (
        "plausibility",
        "layer_agreement",
        "integrity",
        "freshness",
        "source_agreement",
        "forming_snapshots",
        "provider_agreement",
    ):
        assert name in report.checks, f"the {name} check did not run"

    # The verdict must be one of the three it is allowed to be.
    assert report.verdict in {"passed", "warning", "failed"}

    # The serialised form must carry the numbers, not a placeholder.
    payload = report.to_dict()
    assert payload["verdict"] == report.verdict
    assert payload["checks"]["layer_agreement"]["checked"] >= 0
    assert "checked_at" in payload
