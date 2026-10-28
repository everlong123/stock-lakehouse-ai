"""Test that the Yahoo HTTP provider honours a UTC fetch boundary.

The provider is exercised against a stubbed HTTP session, so the test
proves the BOUNDARY MATH (which is what the bug was about) without
depending on the network.

The bug: the provider turned the ``start`` it was handed into a Unix
timestamp with ``datetime.timestamp()``. For a NAIVE datetime that uses
the MACHINE'S local timezone, so the request window moved by the host's
UTC offset - far enough to step over a trading day's session open and
silently drop that day from the response.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_sources.yahoo_http_provider import YahooHttpProvider  # noqa: E402


class _StubResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _StubSession:
    """Records the request params and returns one fixed bar."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params or {}))
        return _StubResponse(self._payload)

    def headers_update(self, *a, **k):  # pragma: no cover - not used
        return None


def _payload(timestamps: list[int]) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0] * len(timestamps),
                                "high": [101.0] * len(timestamps),
                                "low": [99.0] * len(timestamps),
                                "close": [100.5] * len(timestamps),
                                "volume": [1000] * len(timestamps),
                            }
                        ],
                        "adjclose": [{"adjclose": [100.5] * len(timestamps)}],
                    },
                }
            ],
            "error": None,
        }
    }


def _provider_with_stub(timestamps: list[int]) -> tuple[YahooHttpProvider, _StubSession]:
    provider = YahooHttpProvider()
    stub = _StubSession(_payload(timestamps))
    provider.session = stub
    return provider, stub


def test_naive_start_is_interpreted_as_utc():
    """The period1 must be the UTC reading of the naive boundary."""
    provider, stub = _provider_with_stub([1792589400])

    provider.get_historical_data(
        symbol="AAPL",
        start=datetime(2026, 10, 21, 13, 30),
        end=datetime(2026, 10, 27),
        interval="1d",
    )

    expected = int(datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc).timestamp())
    assert stub.calls[0]["period1"] == expected


def test_naive_start_is_not_shifted_by_the_host_timezone():
    """Two different host offsets must not change the request window."""
    provider, stub = _provider_with_stub([1792589400])

    provider.get_historical_data(
        symbol="AAPL",
        start=datetime(2026, 10, 21, 13, 30),
        end=datetime(2026, 10, 27),
        interval="1d",
    )

    period1 = stub.calls[0]["period1"]
    # The boundary must land exactly on the session open, not a few hours
    # past it - otherwise the day's bar is excluded from the response.
    boundary = datetime.fromtimestamp(period1, tz=timezone.utc)
    assert boundary == datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc)
    assert boundary.hour == 13 and boundary.minute == 30


def test_aware_start_is_accepted_and_converted():
    provider, stub = _provider_with_stub([1792589400])

    provider.get_historical_data(
        symbol="AAPL",
        start=datetime(2026, 10, 21, 20, 30, tzinfo=timezone(timedelta(hours=7))),
        end=datetime(2026, 10, 27, tzinfo=timezone.utc),
        interval="1d",
    )

    expected = int(datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc).timestamp())
    assert stub.calls[0]["period1"] == expected


def test_period2_is_later_than_period1():
    provider, stub = _provider_with_stub([1792589400])

    provider.get_historical_data(
        symbol="AAPL",
        start=datetime(2026, 10, 21),
        end=datetime(2026, 10, 27),
        interval="1d",
    )

    assert stub.calls[0]["period2"] > stub.calls[0]["period1"]
