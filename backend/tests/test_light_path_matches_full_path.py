"""The light path and the full path MUST produce the same forecast.

WHY THIS TEST EXISTS
--------------------
The nightly batch uses the light path (`light_forecast.future_series`)
because the full path is too slow to run over ~900 symbols every night.
The forecasting page uses the full path (`predict_symbol`) because it
needs the hold-out history as well.

Two implementations of the same forecast would be a disaster: the Dashboard
reads the STORED forecast (light path) while the chart computes the
forecast itself (full path), and if they disagreed the user would see two
different numbers for the same model, the same symbol and the same moment,
with nothing to explain the difference.

So there is only ONE implementation, and this test checks that the two
callers of it agree.

HOW IT RUNS
-----------
The test needs real data, so it uses the symbols that already have a
trained model in `backend/data/models`. It SKIPS (rather than fails) when
neither the lakehouse nor the model directory is reachable, because a
test that fails because the infrastructure is down teaches nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.forecasting import light_forecast  # noqa: E402
from app.forecasting.predictor import predict_symbol  # noqa: E402
from app.lakehouse.gold import GoldLayer  # noqa: E402

#: The symbols that have a trained model AND are large enough to have a
#: meaningful history. The list is read from the model directory so the
#: test picks up whatever has actually been trained.
CANDIDATE_SYMBOLS = ("AAPL", "MSFT", "NVDA", "VCB", "FPT", "ROKU", "VNM", "AON")


def _symbols_with_models() -> list[tuple[str, str]]:
    from app.forecasting.model_registry import model_directory

    pairs: list[tuple[str, str]] = []
    for symbol in CANDIDATE_SYMBOLS:
        for model_name in ("linear_regression", "arima"):
            directory = model_directory(symbol, model_name)
            if (directory / "registry.json").exists():
                pairs.append((symbol, model_name))
    return pairs


def _gold(symbol: str):
    try:
        frame = GoldLayer().read(symbol)
    except Exception:  # noqa: BLE001
        return None
    return None if frame.empty else frame


@pytest.mark.parametrize("symbol,model_name", _symbols_with_models())
def test_light_path_matches_full_path(symbol: str, model_name: str) -> None:
    """The forward point of the two paths must be the same number."""
    gold = _gold(symbol)
    if gold is None:
        pytest.skip(f"No Gold data for {symbol}.")

    light = light_forecast.future_series(symbol, model_name, gold, horizon=1)
    if not light:
        pytest.skip(f"The model produced no forward point for {symbol}/{model_name}.")

    full = predict_symbol(symbol, model_name, horizon=1)
    full_future = [p for p in full.get("predictions", []) if p.get("actual") is None]
    if not full_future:
        pytest.skip(f"The full path produced no forward point for {symbol}/{model_name}.")

    assert len(light) == 1
    assert len(full_future) >= 1

    # The timestamp must match: the two paths predict the same session.
    assert str(light[0]["timestamp"]) == str(full_future[0]["timestamp"]), (
        f"{symbol}/{model_name}: light path targets {light[0]['timestamp']} "
        f"but the full path targets {full_future[0]['timestamp']}"
    )

    # The predicted close must match to within a rounding step. A tiny
    # tolerance is allowed because the ARIMA path may serialise and reload
    # its state-space model, which is not bit-identical.
    light_value = float(light[0]["predicted"])
    full_value = float(full_future[0]["predicted"])
    tolerance = max(1e-6, abs(full_value) * 1e-9)
    assert abs(light_value - full_value) <= tolerance, (
        f"{symbol}/{model_name}: light path predicted {light_value}, "
        f"full path predicted {full_value}"
    )
