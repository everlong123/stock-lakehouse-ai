"""Dashboard aggregation service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.database.repositories.backtest_repository import BacktestRepository
from app.database.repositories.model_repository import ModelRepository
from app.database.repositories.pipeline_repository import PipelineRepository
from app.database.repositories.prediction_repository import PredictionRepository
from app.database.session import check_database_connection
from app.forecasting.model_registry import list_trained_models
from app.indicators.service import describe_indicators
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer
from app.services.market_service import MarketService

logger = get_logger(__name__)


class DashboardService:
    def __init__(self) -> None:
        self.market = MarketService()

    @staticmethod
    def _layer_counts(symbol: str) -> dict[str, int]:
        """How many stored objects each layer holds for one symbol.

        WHY CONCURRENTLY
        ----------------
        Counting is a metadata operation: the storage backend lists the
        symbol's object keys and counts them, without downloading a single
        parquet payload. For a ten-year daily ticker that is ~122 keys per
        layer, and MinIO answers the listing in 25-80 ms.

        The three layers are independent, so asking them one after another
        made the dashboard pay the SUM of three round-trips. Measured on
        14/11/2026: 82 ms + 27 ms + 72 ms = 181 ms of pure waiting on
        numbers that the page only shows as three small counters.

        Asking them at the same time makes the dashboard pay the SLOWEST
        of the three instead - about 82 ms. The counts themselves are
        unchanged: the same keys are listed, the same objects are counted.
        """
        layers = (
            ("bronze", BronzeLayer()),
            ("silver", SilverLayer()),
            ("gold", GoldLayer()),
        )
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(layer.record_count, symbol): name
                for name, layer in layers
            }
            counts: dict[str, int] = {}
            for future, name in futures.items():
                try:
                    counts[name] = int(future.result())
                except Exception as exc:  # noqa: BLE001 - a counter must not blank the page
                    logger.warning("Dashboard count failed for %s: %s", name, exc)
                    counts[name] = 0
        return counts

    def build(
        self,
        symbol: str,
        db: Session | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        """The dashboard payload for one symbol.

        WHY `start` AND `end` EXIST
        --------------------------
        The stored history of a ten-year daily ticker is ~121 monthly
        parquet partitions. The dashboard draws a 3M/1W window by
        default, so without a window the backend downloaded the whole
        history and the browser threw away most of it.

        With a window, the backend reads only the partitions that can
        hold the requested range and the response shrinks with it. The
        rows are the SAME stored rows - the window changes how much is
        transferred, never what is in the lakehouse.
        """
        history = self.market.get_history(symbol, start=start, end=end)
        # The latest bar is derived from the frame that was just loaded.
        # Calling `get_latest` would read the symbol's whole history a
        # SECOND time.
        latest = self.market.latest_from_frame(symbol, history)
        last = history.iloc[-1]
        rsi_value = None
        if "rsi_14" in history.columns and pd.notna(last["rsi_14"]):
            rsi_value = float(last["rsi_14"])
        summary = describe_indicators(last) if "sma_20" in history.columns else {}
        # 2500 daily bars ≈ 10 years of trading days, which is the full
        # lookback supported by the data sources. The previous cap of 250
        # only returned ~1 year, so long-term trends (2016-2026) were hidden.
        candles = self.market.to_records(history, limit=2500)
        prediction = None
        models = list_trained_models(symbol)
        if models:
            best = models[0]
            prediction = {
                "model_name": best.get("model_name"),
                "mae": best.get("mae"),
                "rmse": best.get("rmse"),
                "mape": best.get("mape"),
                "directional_accuracy": best.get("directional_accuracy"),
            }
        pipeline = None
        backtest = None
        next_session_forecast = None
        published_forecasts = []
        # The historical metric of the model that wrote the forecast the
        # card shows. The Dashboard is a summary, so it shows ONE number
        # plus that number's track record - the full per-model comparison
        # lives on the Models page.
        forecast_model_mae = None
        forecast_model_directional_accuracy = None
        if db is not None and check_database_connection():
            try:
                latest_pipeline = PipelineRepository(db).latest(symbol)
                if latest_pipeline:
                    pipeline = {
                        "status": latest_pipeline.status,
                        "records_processed": latest_pipeline.records_processed,
                        "error_count": latest_pipeline.error_count,
                        "message": latest_pipeline.message,
                        "created_at": latest_pipeline.created_at.isoformat() if latest_pipeline.created_at else None,
                    }
                latest_model = ModelRepository(db).latest(symbol)
                if latest_model:
                    prediction = {
                        "model_name": latest_model.model_name,
                        "mae": latest_model.mae,
                        "rmse": latest_model.rmse,
                        "mape": latest_model.mape,
                        "directional_accuracy": latest_model.directional_accuracy,
                    }
                latest_bt = BacktestRepository(db).latest(symbol)
                if latest_bt:
                    backtest = {
                        "strategy": latest_bt.strategy,
                        "total_return": latest_bt.total_return,
                        "sharpe_ratio": latest_bt.sharpe_ratio,
                        "maximum_drawdown": latest_bt.maximum_drawdown,
                        "win_rate": latest_bt.win_rate,
                    }
                # The next-session forecast stored by the EOD batch. It is
                # read from the `predictions` table, so it is the SAME
                # number the overnight run produced - not a value recomputed
                # for this request, which could differ from the stored one.
                #
                # TWO LEVELS OF DETAIL, ONE SOURCE
                # --------------------------------
                # `next_session_forecast` is the single headline number: the
                # most recent forecast for this symbol, whatever model
                # wrote it. It is what the Dashboard card shows.
                #
                # `published_forecasts` is the full comparison: every model
                # that published a forecast for the SAME session, with the
                # metric each model has historically achieved.
                #
                # Both come from the `predictions` table, so the Dashboard
                # and the forecasting page can never show different numbers
                # for the same forecast. The Dashboard shows one row; the
                # forecasting page shows the table. One source, two levels
                # of detail - not two sources.
                stored_prediction = PredictionRepository(db).latest_for_symbol(symbol)
                if stored_prediction:
                    next_session_forecast = {
                        "symbol": stored_prediction.symbol,
                        "model_name": stored_prediction.model_name,
                        "target_session": stored_prediction.target_session.isoformat()
                        if stored_prediction.target_session
                        else None,
                        "reference_close": stored_prediction.reference_close,
                        "predicted_close": stored_prediction.predicted_close,
                        "predicted_return": stored_prediction.predicted_return,
                        "horizon": stored_prediction.horizon,
                        "source": stored_prediction.source,
                        "source_layer": stored_prediction.source_layer or "gold",
                        # How many trading sessions the input data lagged
                        # behind the target when this forecast was made.
                        # The Dashboard shows a notice when it is non-zero,
                        # so a forecast made on stale data cannot be read
                        # as one made on current data.
                        "data_staleness_days": stored_prediction.data_staleness_days,
                        "created_at": stored_prediction.created_at.isoformat()
                        if stored_prediction.created_at
                        else None,
                    }

                    # The track record of the model that wrote the forecast
                    # above. It is looked up from the trained models, NOT
                    # from the `models` table, so the number describes the
                    # model that actually produced the displayed forecast.
                    for record in models:
                        if record.get("model_name") == stored_prediction.model_name:
                            forecast_model_mae = record.get("mae")
                            forecast_model_directional_accuracy = record.get(
                                "directional_accuracy"
                            )
                            break

                    # The per-model comparison for that same session. The
                    # rows are read with ONE query, not one query per
                    # model.
                    target_session = stored_prediction.target_session
                    if target_session is not None:
                        rows = PredictionRepository(db).for_symbol_and_session(
                            symbol, target_session
                        )
                        published_forecasts = [
                            {
                                "model_name": row.model_name,
                                "target_session": row.target_session.isoformat()
                                if row.target_session
                                else None,
                                "reference_close": row.reference_close,
                                "predicted_close": row.predicted_close,
                                "predicted_return": row.predicted_return,
                                "horizon": row.horizon,
                                "source": row.source,
                                "source_layer": row.source_layer or "gold",
                                "data_staleness_days": row.data_staleness_days,
                                "created_at": row.created_at.isoformat()
                                if row.created_at
                                else None,
                            }
                            for row in rows
                        ]
            except Exception as exc:
                logger.warning("Dashboard metadata lookup failed: %s", exc)
        return {
            "symbol": symbol.upper(),
            "current_price": latest["close"],
            "change_pct": latest["change_pct"],
            "volume": latest["volume"],
            # The quote currency. Prices here are unitless and VCB's 53,500
            # and AAPL's 330 are both "close", so the UI needs to know which
            # unit this symbol's prices are in to label them correctly.
            "currency": latest.get("currency"),
            "rsi": rsi_value,
            "latest_prediction": prediction,
            "latest_backtest": backtest,
            "next_session_forecast": next_session_forecast,
            "published_forecasts": published_forecasts,
            "forecast_model_mae": forecast_model_mae,
            "forecast_model_directional_accuracy": forecast_model_directional_accuracy,
            "pipeline": pipeline,
            "summary": summary,
            "candles": candles,
            "counts": self._layer_counts(symbol),
            "data_source": settings.data_source,
            "disclaimer": (
                "This dashboard is a research prototype. Forecasts and backtests are not investment advice."
            ),
        }
