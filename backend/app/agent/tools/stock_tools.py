"""Pydantic tool I/O schemas and executable tool functions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ALL_SYMBOLS
from app.forecasting.predictor import FORECAST_DISCLAIMER, RISK_ASSESSMENT_DISCLAIMER, GENERAL_DISCLAIMER
from app.services.backtest_service import BacktestService
from app.services.forecasting_service import ForecastingService
from app.services.indicator_service import IndicatorService
from app.services.market_service import MarketService


class StockQueryInput(BaseModel):
    symbol: str = Field(description="Ticker symbol, e.g. AAPL")
    lookback_bars: int = Field(default=60, ge=5, le=500)


class StockQueryOutput(BaseModel):
    symbol: str
    last_close: float
    change_pct: float
    volume: float
    bars: int
    last_timestamp: str


class IndicatorInput(BaseModel):
    symbol: str
    lookback_bars: int = Field(default=60, ge=14, le=500)


class IndicatorOutput(BaseModel):
    symbol: str
    rsi: float | None
    macd: float | None
    sma_20: float | None
    sma_50: float | None
    # The structured facts from `describe_indicators`: three groups, each a
    # `code` plus the numbers it rests on. It is NOT prose — the frontend
    # writes the sentence in the reader's language, and so does the agent.
    summary: dict[str, dict[str, Any]]


class ForecastInput(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    symbol: str
    model_name: str = Field(default="linear_regression")
    horizon: int = Field(default=5, ge=1, le=30)


class ForecastOutput(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    symbol: str
    model_name: str
    metrics: dict[str, Any]
    latest_predicted: float | None
    forecast_available: bool
    forecast_reason: str | None = None
    target_timestamp: str | None = None
    horizon: int
    disclaimer: str


class CompareInput(BaseModel):
    symbol: str


class CompareOutput(BaseModel):
    symbol: str
    models: list[dict[str, Any]]
    note: str


class BacktestInput(BaseModel):
    symbol: str
    strategy: str = Field(default="ma_crossover")
    initial_capital: float = 10000


class BacktestOutput(BaseModel):
    symbol: str
    strategy: str
    total_return: float
    win_rate: float
    sharpe_ratio: float
    maximum_drawdown: float
    number_of_trades: int
    # WHY THE *_pct FIELDS EXIST
    # ---------------------------
    # `total_return` is a FRACTION (3.2005 means +320.05%). The model reads
    # the raw tool payload and writes the number into prose, so it used to
    # write "Total Return: 3.20%" for a +320.05% backtest - off by two
    # orders of magnitude. The fraction stays for the code, and the
    # already-converted percentage is added next to it so the model has a
    # number it can quote without doing the arithmetic itself.
    total_return_pct: float
    win_rate_pct: float
    maximum_drawdown_pct: float
    disclaimer: str


class MarketSummaryInput(BaseModel):
    symbol: str = Field(default="AAPL")


class MarketSummaryOutput(BaseModel):
    symbol: str
    close: float
    change_pct: float
    volume: float
    rsi: float | None


def _normalize_symbol(symbol: str) -> str:
    """Upper-case the ticker.

    ``ALL_SYMBOLS`` (which includes the Vietnamese tickers, the crypto pairs
    and the market indexes) is the reference universe. The tool still accepts
    a symbol outside it, because the lakehouse may hold data for a ticker
    that was never added to the curated list — the membership check is a
    sanity signal, not a gate.
    """
    value = symbol.upper().strip()
    if value not in ALL_SYMBOLS:
        # Allow unknown tickers if lakehouse already has data.
        return value
    return value


def query_stock_data(symbol: str, lookback_bars: int = 60) -> dict[str, Any]:
    market = MarketService()
    symbol = _normalize_symbol(symbol)
    history = market.get_history(symbol).tail(lookback_bars)
    latest = market.get_latest(symbol)
    payload = StockQueryOutput(
        symbol=symbol,
        last_close=latest["close"],
        change_pct=latest["change_pct"],
        volume=latest["volume"],
        bars=int(len(history)),
        last_timestamp=latest["timestamp"],
    )
    return payload.model_dump()


def calculate_indicators(symbol: str, lookback_bars: int = 60) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    data = IndicatorService().calculate(symbol)
    latest = data["latest"]
    payload = IndicatorOutput(
        symbol=symbol,
        rsi=latest.get("rsi_14"),
        macd=latest.get("macd"),
        sma_20=latest.get("sma_20"),
        sma_50=latest.get("sma_50"),
        summary=data["summary"],
    )
    return payload.model_dump()


def forecast_stock(symbol: str, model_name: str = "linear_regression", horizon: int = 5) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    result = ForecastingService().predict(symbol, model_name, horizon)
    # Historical holdout points share this array with future points.
    # A historical estimate must never stand in for a rejected forecast.
    future = [
        point for point in result.get("predictions", [])
        if point.get("actual") is None and point.get("predicted") is not None
    ] if result.get("forecast_available") else []
    latest = future[-1] if future else {}
    payload = ForecastOutput(
        symbol=symbol,
        model_name=model_name,
        metrics=result.get("metrics") or {},
        latest_predicted=latest.get("predicted"),
        forecast_available=bool(future),
        forecast_reason=result.get("forecast_reason"),
        target_timestamp=latest.get("timestamp"),
        horizon=horizon,
        disclaimer=result.get("disclaimer", ""),
    )
    return payload.model_dump()


def compare_models(symbol: str) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    result = ForecastingService().compare(symbol)
    payload = CompareOutput(symbol=symbol, models=result.get("models") or [], note=result.get("note", ""))
    return payload.model_dump()


def run_backtest(symbol: str, strategy: str = "ma_crossover", initial_capital: float = 10000) -> dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    result = BacktestService().run(
        {
            "symbol": symbol,
            "strategy": strategy,
            "initial_capital": initial_capital,
        }
    )

    # Build comprehensive disclaimer
    disclaimer = f"""
{result.get('disclaimer', '')}

{RISK_ASSESSMENT_DISCLAIMER}

{GENERAL_DISCLAIMER}
"""

    payload = BacktestOutput(
        symbol=symbol,
        strategy=strategy,
        total_return=result["total_return"],
        win_rate=result["win_rate"],
        sharpe_ratio=result["sharpe_ratio"],
        maximum_drawdown=result["maximum_drawdown"],
        number_of_trades=result["number_of_trades"],
        total_return_pct=round(float(result["total_return"]) * 100, 2),
        win_rate_pct=round(float(result["win_rate"]) * 100, 2),
        maximum_drawdown_pct=round(float(result["maximum_drawdown"]) * 100, 2),
        disclaimer=disclaimer,
    )
    return payload.model_dump()


def get_market_summary(symbol: str = "AAPL") -> dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    latest = MarketService().get_latest(symbol)
    indicators = IndicatorService().calculate(symbol)
    payload = MarketSummaryOutput(
        symbol=symbol,
        close=latest["close"],
        change_pct=latest["change_pct"],
        volume=latest["volume"],
        rsi=indicators["latest"].get("rsi_14"),
    )
    return payload.model_dump()
