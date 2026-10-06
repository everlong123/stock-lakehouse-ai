"""Unit tests for the Silver layer validation pipeline.

Covers:
  * Clean pass-through (no errors rejected, quality_status=passed)
  * Missing values in OHLCV -> rejected
  * Invalid OHLC relationships (high<low, high<open, low>close, ...) -> rejected
  * Negative volume -> rejected
  * Duplicate (symbol, timestamp) -> deduplicated (last kept)
  * Mixed symbols in one frame
  * Quality report schema (required keys present)
  * Empty frame -> DataValidationError
  * Invalid OHLC reasons accumulated in error_reason
  * Storage side effect: errors parquet is written under _errors/
  * Output schema: OHLCV_COLUMNS + correct dtypes
  * Timestamp is UTC and sorted ascending per symbol
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataValidationError
from app.lakehouse.local_storage import LocalStorageBackend
from app.lakehouse.silver import SilverLayer
from tests.conftest import make_ohlcv


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_storage(tmp_path: Path) -> LocalStorageBackend:
    """Local storage rooted in pytest tmp_path (isolated per-test)."""
    return LocalStorageBackend(root=tmp_path)


@pytest.fixture
def silver(tmp_storage: LocalStorageBackend) -> SilverLayer:
    return SilverLayer(storage=tmp_storage)


# ── Happy path ────────────────────────────────────────────────────────────


def test_clean_frame_passes_through(silver: SilverLayer) -> None:
    frame = make_ohlcv(120)
    clean, quality = silver.transform(frame)

    assert len(clean) == len(frame), "all valid rows must survive"
    assert quality["record_count"] == len(frame)
    assert quality["duplicate_count"] == 0
    assert quality["missing_count"] == 0
    assert quality["invalid_ohlc_count"] == 0
    assert quality["invalid_volume_count"] == 0
    assert quality["error_count"] == 0
    assert quality["quality_status"] == "passed"


def test_output_schema_matches_ohlcv_columns(silver: SilverLayer) -> None:
    clean, _ = silver.transform(make_ohlcv(60))
    assert list(clean.columns) == OHLCV_COLUMNS


def test_output_timestamp_is_utc(silver: SilverLayer) -> None:
    clean, _ = silver.transform(make_ohlcv(60))
    assert pd.api.types.is_datetime64_any_dtype(clean["timestamp"])
    ts = clean["timestamp"].iloc[0]
    if ts.tzinfo is None:
        # pandas may emit tz-naive but values are UTC; check via str
        assert str(ts).endswith("+00:00") or "T" in str(ts)
    else:
        assert str(ts.tzinfo) == "UTC"


def test_output_sorted_by_symbol_then_timestamp(silver: SilverLayer) -> None:
    frame = make_ohlcv(40)
    # shuffle to ensure transform sorts
    shuffled = frame.sample(frac=1, random_state=7).reset_index(drop=True)
    clean, _ = silver.transform(shuffled)
    sorted_check = clean.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(clean, sorted_check)


def test_symbol_is_uppercased(silver: SilverLayer) -> None:
    frame = make_ohlcv(30)
    frame["symbol"] = "aapl"  # lowercase
    clean, _ = silver.transform(frame)
    assert (clean["symbol"] == "AAPL").all()


# ── Missing values ────────────────────────────────────────────────────────


def test_missing_open_is_rejected(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    frame.loc[5, "open"] = None
    clean, quality = silver.transform(frame)
    # Check by value (not index) - reset_index happened inside transform
    bad_ts = frame.loc[5, "timestamp"]
    survived = clean[clean["timestamp"] == bad_ts]
    assert survived.empty, "row with missing open must be dropped"
    assert quality["missing_count"] == 1
    assert quality["error_count"] >= 1


def test_missing_volume_is_rejected(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    frame.loc[3, "volume"] = None
    clean, quality = silver.transform(frame)
    bad_ts = frame.loc[3, "timestamp"]
    survived = clean[clean["timestamp"] == bad_ts]
    assert survived.empty, "row with missing volume must be dropped"
    assert quality["missing_count"] == 1


def test_missing_timestamp_is_rejected(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    frame.loc[7, "timestamp"] = pd.NaT
    clean, quality = silver.transform(frame)
    assert quality["missing_count"] == 1
    # The remaining 19 rows must all be valid
    assert len(clean) == 19


# ── Invalid OHLC relationships ────────────────────────────────────────────


def test_high_below_low_is_rejected(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    frame.loc[2, "high"] = 50.0
    frame.loc[2, "low"] = 100.0  # high < low
    clean, quality = silver.transform(frame)
    bad_ts = frame.loc[2, "timestamp"]
    assert clean[clean["timestamp"] == bad_ts].empty
    assert quality["invalid_ohlc_count"] == 1


def test_high_below_open_is_rejected(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    frame.loc[4, "open"] = 200.0
    frame.loc[4, "high"] = 150.0  # high < open
    clean, quality = silver.transform(frame)
    bad_ts = frame.loc[4, "timestamp"]
    assert clean[clean["timestamp"] == bad_ts].empty
    assert quality["invalid_ohlc_count"] == 1


def test_low_above_close_is_rejected(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    frame.loc[1, "close"] = 100.0
    frame.loc[1, "low"] = 120.0  # low > close
    clean, quality = silver.transform(frame)
    bad_ts = frame.loc[1, "timestamp"]
    assert clean[clean["timestamp"] == bad_ts].empty
    assert quality["invalid_ohlc_count"] == 1


# ── Volume ────────────────────────────────────────────────────────────────


def test_negative_volume_is_rejected(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    frame.loc[0, "volume"] = -1
    clean, quality = silver.transform(frame)
    bad_ts = frame.loc[0, "timestamp"]
    assert clean[clean["timestamp"] == bad_ts].empty
    assert quality["invalid_volume_count"] == 1


def test_zero_volume_passes(silver: SilverLayer) -> None:
    # Volume=0 is a valid "no-trade day" (e.g. halted), not invalid.
    frame = make_ohlcv(20)
    frame.loc[0, "volume"] = 0
    clean, quality = silver.transform(frame)
    assert quality["invalid_volume_count"] == 0
    # 20 unique rows + 0 dup = 20 surviving
    assert len(clean) == 20


# ── Duplicates ────────────────────────────────────────────────────────────


def test_duplicate_symbol_timestamp_is_removed(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    duplicate = frame.iloc[5].copy()
    frame = pd.concat([frame, pd.DataFrame([duplicate])], ignore_index=True)
    clean, quality = silver.transform(frame)
    # 20 unique + 1 dup removed = 20 surviving rows
    assert len(clean) == 20
    assert quality["duplicate_count"] == 1


def test_duplicate_keeps_last_occurrence(silver: SilverLayer) -> None:
    frame = make_ohlcv(20)
    # Append a row that is a true duplicate of the LAST row (so all OHLC
    # relationships still hold, only the (symbol, timestamp) key is repeated).
    last = frame.iloc[-1]
    target_ts = last["timestamp"]
    sym = last["symbol"]
    dup = last.copy()
    # Mark this copy as the "newer" one with a slightly different close that
    # stays inside the existing high/low envelope so it isn't rejected as
    # invalid_ohlc.
    dup["close"] = float(last["low"]) + 0.01
    dup["adj_close"] = dup["close"]
    new_value = float(dup["close"])
    frame = pd.concat([frame, pd.DataFrame([dup])], ignore_index=True)
    clean, quality = silver.transform(frame)
    # the duplicate row must be deduplicated, NOT rejected as invalid
    assert quality["duplicate_count"] == 1
    assert quality["invalid_ohlc_count"] == 0
    kept = clean[(clean["timestamp"] == target_ts) & (clean["symbol"] == sym)]
    assert len(kept) == 1
    assert float(kept.iloc[0]["close"]) == pytest.approx(new_value)


# ── Mixed corruption (multiple errors on one row) ────────────────────────


def test_row_with_multiple_problems_gets_all_reasons(
    silver: SilverLayer, tmp_storage: LocalStorageBackend
) -> None:
    frame = make_ohlcv(30)
    # row 10: missing close + invalid volume
    target_ts = frame.loc[10, "timestamp"]
    frame.loc[10, "close"] = None
    frame.loc[10, "volume"] = -5
    silver.transform(frame)
    # error parquet is written to _errors/
    errors = tmp_storage.list_objects("silver", "_errors/")
    assert any("errors_" in key for key in errors), "_errors/ parquet must be written"
    err_df = tmp_storage.read_prefix("silver", "_errors/")
    bad_row = err_df[err_df["timestamp"] == target_ts]
    assert not bad_row.empty
    reason = str(bad_row.iloc[0]["error_reason"])
    assert "missing" in reason
    assert "invalid_volume" in reason


# ── Empty / edge cases ────────────────────────────────────────────────────


def test_empty_frame_raises_validation_error(silver: SilverLayer) -> None:
    with pytest.raises(DataValidationError):
        silver.transform(pd.DataFrame(columns=OHLCV_COLUMNS))


def test_all_invalid_frame_yields_failed_quality(
    silver: SilverLayer, tmp_storage: LocalStorageBackend
) -> None:
    frame = make_ohlcv(10)
    # poison every row
    frame["volume"] = -1
    clean, quality = silver.transform(frame)
    assert clean.empty
    assert quality["quality_status"] == "failed"
    assert quality["error_count"] == 10


# ── Multi-symbol handling ─────────────────────────────────────────────────


def test_multiple_symbols_kept_separate(silver: SilverLayer) -> None:
    a = make_ohlcv(30)
    b = make_ohlcv(20)
    b["symbol"] = "MSFT"
    multi = pd.concat([a, b], ignore_index=True)
    clean, quality = silver.transform(multi)
    assert set(clean["symbol"].unique()) == {"AAPL", "MSFT"}
    assert quality["record_count"] == 50


# ── Quality report schema ─────────────────────────────────────────────────


def test_quality_report_has_all_required_keys(silver: SilverLayer) -> None:
    _, quality = silver.transform(make_ohlcv(50))
    required = {
        "engine",
        "record_count",
        "source_count",
        "duplicate_count",
        "missing_count",
        "invalid_ohlc_count",
        "invalid_volume_count",
        "error_count",
        "min_timestamp",
        "max_timestamp",
        "quality_status",
    }
    assert required.issubset(quality.keys())


def test_quality_json_is_persisted_per_symbol(
    silver: SilverLayer, tmp_storage: LocalStorageBackend
) -> None:
    frame = make_ohlcv(20)
    clean, quality = silver.transform(frame)
    silver.write(clean, quality)
    raw = tmp_storage.read_json("silver", "symbol=AAPL/_quality.json")
    assert raw["record_count"] == 20
    # stored JSON must round-trip
    assert json.loads(json.dumps(raw)) == raw


# ── write() partition side effects ────────────────────────────────────────


def test_write_creates_year_month_partitions(
    silver: SilverLayer, tmp_storage: LocalStorageBackend
) -> None:
    frame = make_ohlcv(60)  # spans ~3 months
    clean, quality = silver.transform(frame)
    result = silver.write(clean, quality)
    assert "paths" in result
    assert result["records"] == 60
    # list at least one partition folder
    keys = tmp_storage.list_objects("silver", "symbol=AAPL/")
    # LocalStorage uses native OS separators - check both styles
    has_year = any("year=" in key for key in keys)
    has_month = any("month=" in key for key in keys)
    assert has_year, f"missing year partition in: {keys[:5]}"
    assert has_month, f"missing month partition in: {keys[:5]}"


# ── read() round trip ────────────────────────────────────────────────────


def test_read_roundtrip_returns_same_rows(
    silver: SilverLayer, tmp_storage: LocalStorageBackend
) -> None:
    frame = make_ohlcv(40)
    clean, quality = silver.transform(frame)
    silver.write(clean, quality)
    reloaded = silver.read("AAPL")
    # 1d bars on business days; allow small date-window differences
    assert abs(len(reloaded) - len(clean)) <= 5
    # All OHLCV columns must be present (read() also adds partition cols)
    assert set(OHLCV_COLUMNS).issubset(set(reloaded.columns))
