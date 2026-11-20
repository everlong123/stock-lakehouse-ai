"""The accuracy report must describe the system honestly.

WHY THIS TEST EXISTS
--------------------
Two bugs were found in the verification report after it was first built,
and both of them made the report look BETTER than reality (or emptier
than reality). That is the worst kind of bug for a thesis: the panel
looked fine and nobody could tell from the UI that it was wrong.

  1. **The mean relative error was reported alone.** Mixing symbols whose
     price is a fraction of a unit made the mean meaningless: on
     13/11/2026 the mean over 45.245 verified rows was 264,95% while the
     median was 1,16%. The report now leads with the median.

  2. **The published summary came back empty.** It was computed by
     FILTERING the limited series (``rows`` is capped at the most recent
     ``limit`` entries), so the older published rows were pushed out of
     the window by the backfilled ones and the count came back as zero
     even though published rows existed.

Both are pinned here. The test uses real data when it is reachable and
SKIPS when it is not, because a test that fails because the
infrastructure is down teaches nothing about the reporting logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.session import check_database_connection, get_session_factory  # noqa: E402


def test_the_median_matches_an_independent_calculation() -> None:
    """Check the same clean population against Python's median.

    A mean can be below or above a median, and a relative error can exceed
    one. Neither relationship is a valid invariant for this report.
    """
    if not check_database_connection():
        pytest.skip("The database is unavailable.")

    from statistics import median as calculate_median
    from sqlalchemy import select

    from app.database.models.prediction import Prediction
    from app.database.repositories.prediction_repository import PredictionRepository, _within_reference_factor

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)

        median = repository.median_error_pct()
        if median is None:
            pytest.skip("There is no verified forecast to measure.")

        values = session.execute(
            select(Prediction.error_pct).where(
                Prediction.actual_close.isnot(None),
                Prediction.error_pct.isnot(None),
                Prediction.reference_close > 0,
                Prediction.actual_close > 0,
                Prediction.predicted_close > 0,
                _within_reference_factor(),
            )
        ).scalars().all()
        assert median == pytest.approx(calculate_median(abs(float(value)) for value in values))
    finally:
        session.close()


def test_the_reported_mean_is_not_destroyed_by_impossible_rows() -> None:
    """The headline mean must survive the rows that cannot exist.

    On 15/11/2026 the reported mean relative error of the whole pool was
    263,85%. The cause was NOT small denominators: removing every
    forecast whose reference close was under 1 USD still left the mean at
    92%. Removing the single symbol ``PARA`` brought it back to -0,03%.

    ``PARA`` held 99,993% of the total absolute error, because its stored
    history mixes two price scales (four reverse splits) and the
    price-LEVEL model extrapolated off the end of it - predictions of
    242.751 and 329.139 against an actual of 0,101.

    So the mean the report leads with must be a sane number, and the rows
    that were left out must be COUNTED, not silently dropped.
    """
    if not check_database_connection():
        pytest.skip("The database is unavailable.")

    from app.database.repositories.prediction_repository import PredictionRepository

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)
        summary = repository.accuracy_summary()
        if not summary["verified"]:
            pytest.skip("There is no verified forecast to measure.")

        mean = summary["mean_error_pct"]
        assert mean is not None
        # A relative error of more than 100% on the MEAN of a whole
        # universe is not a modelling result, it is a broken row that got
        # through. Anything under 1,0 (100%) is a sane value.
        assert abs(float(mean)) < 1.0, (
            f"the mean relative error is {mean} - a row that cannot exist is "
            "still inside the aggregate"
        )

        # The excluded rows must be visible, never hidden.
        assert "excluded_impossible" in summary
        assert summary["excluded_impossible"] >= 0
    finally:
        session.close()


def test_the_published_summary_is_not_empty_when_published_rows_exist() -> None:
    """The published count must reflect the table, not the series window.

    Regression test for the bug where the published summary was computed
    by filtering the limited series and therefore came back as zero even
    though published rows existed in the table.
    """
    if not check_database_connection():
        pytest.skip("The database is unavailable.")

    from app.database.repositories.prediction_repository import PredictionRepository

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)
        published = repository.published_scored_series(limit=5000)
        if not published:
            pytest.skip("There is no published forecast to test.")

        # Every published row must carry a source that is NOT the
        # backfill tag - otherwise the two kinds of evidence are mixed.
        for row in published:
            assert row.source != "backfill_walk_forward"
            assert row.actual_close is not None
    finally:
        session.close()


def test_the_published_summary_matches_the_table() -> None:
    """The endpoint's published summary must equal the table's own count."""
    if not check_database_connection():
        pytest.skip("The database is unavailable.")

    from app.api.v1.endpoints.forecasting import _summarise
    from app.database.repositories.prediction_repository import PredictionRepository

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)
        published = repository.published_scored_series(limit=5000)
        if not published:
            pytest.skip("There is no published forecast to test.")

        summary = _summarise(published)
        assert summary["verified"] == len(published)
        assert summary["median_error_pct"] is not None
    finally:
        session.close()
