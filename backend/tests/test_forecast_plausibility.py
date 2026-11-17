"""Tests for the forecast plausibility guard.

WHY THESE TESTS EXIST
---------------------
On 15/11/2026 the verification ledger was found to hold nineteen forecasts
whose predicted price was negative - LCID at -4,09, SOXS at -359.121.248 -
and one symbol (``PARA``) held 99,993% of the total absolute error of all
44.676 verified rows, because its history mixes two price scales and the
price-level model extrapolated off the end of it.

These tests pin the guard that stops that from happening again.
"""

from __future__ import annotations

import pytest

from app.core.data_integrity import (
    MAX_PREDICTION_REFERENCE_FACTOR,
    is_impossible_price,
)


def test_a_normal_forecast_is_allowed() -> None:
    assert is_impossible_price(102.5, 100.0) is False


def test_a_small_move_is_allowed() -> None:
    assert is_impossible_price(0.104, 0.101) is False


def test_a_negative_forecast_is_rejected() -> None:
    assert is_impossible_price(-4.09, 3.61) is True


def test_a_zero_forecast_is_rejected() -> None:
    assert is_impossible_price(0.0, 3.61) is True


def test_an_absurd_forecast_is_rejected() -> None:
    # SOXS was predicted at -359,121,248 against a reference of 45.72.
    assert is_impossible_price(-359_121_248.0, 45.72) is True


def test_a_scale_mismatch_forecast_is_rejected() -> None:
    # A price-level model that extrapolated across a reverse split.
    assert is_impossible_price(242_751.0, 0.101) is True


def test_a_real_large_move_is_allowed() -> None:
    # PARA traded 0,104 -> 0,319 -> 2,72 inside three real sessions in
    # November 2026 - a 26x move that a tighter bound would reject.
    assert is_impossible_price(2.72, 0.104) is False


def test_the_bound_is_symmetric() -> None:
    # A forecast far BELOW the reference is as broken as one far above.
    assert is_impossible_price(0.001, 100.0) is True


def test_a_missing_forecast_is_rejected() -> None:
    assert is_impossible_price(None, 100.0) is True


def test_a_non_positive_reference_is_rejected() -> None:
    # The anchor itself is broken, so the forecast means nothing.
    assert is_impossible_price(10.0, 0.0) is True
    assert is_impossible_price(10.0, -5.0) is True


def test_a_non_finite_forecast_is_rejected() -> None:
    assert is_impossible_price(float("nan"), 100.0) is True
    assert is_impossible_price(float("inf"), 100.0) is True


def test_a_forecast_without_a_reference_is_only_checked_for_sign() -> None:
    assert is_impossible_price(100.0, None) is False
    assert is_impossible_price(-100.0, None) is True


def test_the_bound_is_documented_and_stable() -> None:
    # If this number changes, the reason has to be written down again.
    assert MAX_PREDICTION_REFERENCE_FACTOR == 100.0
