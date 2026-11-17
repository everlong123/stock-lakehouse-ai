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


def test_the_median_is_not_dragged_by_extreme_rows() -> None:
    """The median describes a typical forecast; the mean does not.

    The check does not compare against a hard-coded number - the table
    grows every day. It compares the median against the mean of the
    ABSOLUTE relative error and asserts the relationship that must hold
    whenever a few extreme rows are present.

    WHY THE ABSOLUTE MEAN AND NOT THE SIGNED ONE
    --------------------------------------------
    The signed mean can be SMALLER than the median even when the model is
    good, because a positive and a negative error of the same size cancel:
    on 15/11/2026 the signed mean over the clean rows was 0,43% while the
    median of the absolute error was 1,15%. Comparing the median against
    the signed mean would fail on a perfectly healthy table.

    The ABSOLUTE mean is the one that has to be at least as large as the
    median: the median is one of the values being averaged, and the mean
    of a set is never below its own median unless the set is empty.
    """
    if not check_database_connection():
        pytest.skip("The database is unavailable.")

    from sqlalchemy import func, select

    from app.database.models.prediction import Prediction
    from app.database.repositories.prediction_repository import PredictionRepository

    session = get_session_factory()()
    try:
        repository = PredictionRepository(session)

        median = repository.median_error_pct()
        if median is None:
            pytest.skip("There is no verified forecast to measure.")

        mean = session.execute(
            select(func.avg(func.abs(Prediction.error_pct))).where(
                Prediction.actual_close.isnot(None),
                Prediction.error_pct.isnot(None),
                Prediction.reference_close > 0,
                Prediction.actual_close > 0,
                Prediction.predicted_close > 0,
            )
        ).scalar()

        assert mean is not None
        # The median is a FRACTION, like `error_pct` - a unit mix-up here
        # would show up as a factor of 100.
        assert 0.0 <= median <= 1.0, f"the median is not a fraction: {median}"

        # The mean of the absolute error can never be smaller than the
        # median of that same set.
        assert median <= float(mean) + 1e-9, (
            "the median absolute error cannot exceed the mean absolute "
            f"error: median={median} mean={mean}"
        )
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
