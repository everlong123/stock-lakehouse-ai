"""The verification ledger must only hold forecasts a real market backs up.

WHY THIS TEST EXISTS
--------------------
On 15/11/2026 the ``predictions`` table was found to hold 200 rows for
the symbols ``TST0`` .. ``TST199``. Every one of them carried the same
invented numbers - ``reference_close = 100.0``, ``predicted_close = 101.0``
- and every one of them was tagged ``source = "auto_eod_batch"``, the tag
that means "the system published this before the session opened".

    10|The Dashboard's "verified" count included them, and nothing in the
table distinguished them from real published forecasts. That is the worst
kind of defect for a thesis: the panel looked fine and the numbers were
not.

Two failure modes are pinned here:

  1. **The write path refuses a fabricated symbol.** A forecast for
     ``TST0`` must be rejected, so the rows cannot come back.

  2. **The table contains no orphan symbol.** Every symbol in the ledger
     must exist in the Gold layer, because a forecast is derived from an
     instrument's history and verified against that instrument's real
     close. A symbol that does not exist in the lakehouse has neither.

The tests use real data when it is reachable and SKIP when it is not,
because a test that fails because the infrastructure is down teaches
nothing about the integrity rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.data_integrity import is_fabricated_symbol  # noqa: E402


def test_a_test_fixture_symbol_is_recognised() -> None:
    """The markers that were actually used are recognised."""
    for symbol in ("TST0", "TST199", "TEST-AAPL", "DEMO1", "MOCK_1", "FAKE", "dummy"):
        assert is_fabricated_symbol(symbol), f"{symbol} should be rejected"


def test_a_real_ticker_is_not_treated_as_a_fixture() -> None:
    """No real listing starts with one of the markers."""
    for symbol in ("AAPL", "VCB", "BRK-B", "MSFT", "7203.T", "0700.HK", "BTC-USD"):
        assert not is_fabricated_symbol(symbol), f"{symbol} should be allowed"


def test_the_write_path_refuses_a_fabricated_symbol() -> None:
    """A forecast for a symbol that does not exist cannot be stored."""
    from app.database.repositories.prediction_repository import PredictionRepository

    class _FakeSession:
        """Just enough of a session to reach the guard."""

        def scalars(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("the guard must fire before the database is touched")

        def add(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("the guard must fire before the row is added")

    repository = PredictionRepository(_FakeSession())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="not a market ticker"):
        repository.upsert(
            {
                "symbol": "TST0",
                "model_name": "linear_regression",
                "target_session": "2026-11-16",
                "reference_close": 100.0,
                "predicted_close": 101.0,
                "predicted_return": 0.01,
                "horizon": 1,
                "source": "auto_eod_batch",
                "source_layer": "gold",
            }
        )


def test_the_write_path_refuses_a_negative_price() -> None:
    """A forecast below zero cannot be stored.

    On 15/11/2026 the ledger held nineteen forecasts whose predicted price
    was negative - LCID at -4,09, SOXS at -359.121.248 - produced by a
    price-level model fitted on a history that mixes two price scales. A
    negative price is not a large error, it is a value no exchange can
    print, and it poisons every mean computed over the table.
    """
    from app.database.repositories.prediction_repository import PredictionRepository

    class _FakeSession:
        """Just enough of a session to reach the guard."""

        def scalars(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("the guard must fire before the database is touched")

        def add(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("the guard must fire before the row is added")

    repository = PredictionRepository(_FakeSession())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="not a price an exchange"):
        repository.upsert(
            {
                "symbol": "LCID",
                "model_name": "linear_regression",
                "target_session": "2026-11-16",
                "reference_close": 3.61,
                "predicted_close": -4.09,
                "predicted_return": -2.13,
                "horizon": 1,
                "source": "auto_eod_batch",
                "source_layer": "gold",
            }
        )


def test_the_write_path_refuses_a_scale_mismatch() -> None:
    """A forecast that is orders of magnitude off its anchor cannot be stored.

    ``PARA`` was predicted at 242.751 against a reference of 0,072 because
    its stored history mixes two price scales. That single row held
    99,993% of the total absolute error of the whole table.
    """
    from app.database.repositories.prediction_repository import PredictionRepository

    class _FakeSession:
        def scalars(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("the guard must fire before the database is touched")

        def add(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("the guard must fire before the row is added")

    repository = PredictionRepository(_FakeSession())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="not a price an exchange"):
        repository.upsert(
            {
                "symbol": "PARA",
                "model_name": "linear_regression",
                "target_session": "2026-11-16",
                "reference_close": 0.072,
                "predicted_close": 242_751.0,
                "predicted_return": 3_371_539.0,
                "horizon": 1,
                "source": "auto_eod_batch",
                "source_layer": "gold",
            }
        )


def test_the_write_path_accepts_a_real_large_move() -> None:
    """A real 26x move must NOT be caught by the guard.

    ``PARA`` traded 0,104 -> 0,164 -> 0,319 -> 2,72 inside three real
    sessions in November 2026. A bound tighter than 100x would reject that
    move and accuse the system of a fault it does not have.
    """
    from app.database.repositories.prediction_repository import PredictionRepository

    class _FakeSession:
        def scalars(self, *args, **kwargs):  # noqa: ANN002, ANN003
            class _Empty:
                def first(self):
                    return None

            return _Empty()

        def add(self, *args, **kwargs):  # noqa: ANN002, ANN003
            pass

        def flush(self, *args, **kwargs):  # noqa: ANN002, ANN003
            pass

    repository = PredictionRepository(_FakeSession())  # type: ignore[arg-type]

    # The guard must not raise: the row goes through the write path.
    repository.upsert(
        {
            "symbol": "PARA",
            "model_name": "linear_regression",
            "target_session": "2026-11-16",
            "reference_close": 0.104,
            "predicted_close": 2.72,
            "predicted_return": 25.15,
            "horizon": 1,
            "source": "auto_eod_batch",
            "source_layer": "gold",
        }
    )


def test_the_table_holds_no_symbol_without_market_data() -> None:
    """Every forecast in the ledger must be about an instrument that exists."""
    from app.core.data_integrity import FABRICATED_SYMBOL_PREFIXES
    from app.database.repositories.prediction_repository import PredictionRepository
    from app.database.session import check_database_connection, get_session_factory

    if not check_database_connection():
        pytest.skip("The database is unavailable.")

    try:
        from app.lakehouse.storage_factory import get_storage_backend

        storage = get_storage_backend()
        gold: set[str] = set()
        for key in storage.list_objects("gold", "symbol="):
            name = str(key)
            if name.startswith("symbol="):
                gold.add(name.split("=", 1)[1].split("/", 1)[0])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"The Gold layer is unavailable: {exc}")

    if not gold:
        pytest.skip("The Gold layer is empty.")

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)
        symbols = {row.symbol for row in repository.recent(limit=5000)}

        fabricated = sorted(symbol for symbol in symbols if is_fabricated_symbol(symbol))
        assert not fabricated, f"the ledger still holds test-fixture symbols: {fabricated}"

        orphans = sorted(symbol for symbol in symbols if symbol not in gold)
        assert not orphans, (
            f"the ledger holds symbols with no data in the Gold layer: {orphans} "
            f"(the markers are {', '.join(FABRICATED_SYMBOL_PREFIXES)})"
        )
    finally:
        session.close()
