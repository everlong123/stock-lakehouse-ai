"""Factory for the configured market data provider.

All providers return **real market data** only - there is no offline/synthetic
fallback.  When ``DATA_SOURCE`` is unset or invalid the factory falls back to
``yfinance`` (the official Python package), which is free, key-less and
returns > 10 years of OHLCV history for every supported US ticker.

Supported ``DATA_SOURCE`` values:

    - ``yfinance``       -> :class:`YFinancePythonProvider` (official ``yfinance`` package).
    - ``finnhub``        -> :class:`FinnhubProvider` (Free tier, 60 req/min).
    - ``alpha_vantage``  -> :class:`AlphaVantageProvider` (Free tier, key required).
    - ``web_scraper``    -> :class:`StockScraperProvider` (HTTP scrape, no key).
    - ``ssi_vn``         -> :class:`SSIVNProvider` (SSI iBoard, HOSE/HNX/UPCOM).
    - ``multi_source``   -> :class:`MultiSourceProvider` (failover chain).
"""

from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger
from app.data_sources.alpha_vantage_provider import AlphaVantageProvider
from app.data_sources.base import StockDataProvider
from app.data_sources.finnhub_provider import FinnhubProvider
from app.data_sources.multi_source import MultiSourceProvider
from app.data_sources.ssi_vn_provider import SSIVNProvider
from app.data_sources.stooq_provider import StooqProvider
from app.data_sources.web_scraper_provider import StockScraperProvider
from app.data_sources.yahoo_http_provider import YahooHttpProvider
from app.data_sources.yfinance_python_provider import YFinancePythonProvider

logger = get_logger(__name__)


def get_data_provider(name: str | None = None) -> StockDataProvider:
    """Return the provider selected by ENV or explicit name.

    Raises :class:`DataSourceError` if the requested provider cannot be
    instantiated (e.g. Alpha Vantage without an API key).
    """

    selected = (name or settings.data_source or "yfinance").lower()

    if selected == "sample":
        raise DataSourceError(
            "DATA_SOURCE=sample is no longer supported - this project ships "
            "ONLY real market data. Use one of: yfinance, finnhub, "
            "alpha_vantage, web_scraper, ssi_vn, multi_source."
        )

    if selected == "multi_source":
        logger.info("Using MultiSourceProvider (failover chain of real APIs).")
        return MultiSourceProvider()

    if selected == "yfinance":
        logger.info("Using YFinancePythonProvider (official yfinance package).")
        return YFinancePythonProvider()

    if selected == "alpha_vantage":
        if not settings.alpha_vantage_api_key:
            raise DataSourceError(
                "DATA_SOURCE=alpha_vantage requires ALPHA_VANTAGE_API_KEY in .env "
                "(free key at https://www.alphavantage.co/support/#api-key)."
            )
        logger.info("Using AlphaVantageProvider.")
        return AlphaVantageProvider()

    if selected == "finnhub":
        if not settings.finnhub_api_key:
            raise DataSourceError(
                "DATA_SOURCE=finnhub requires FINNHUB_API_KEY in .env "
                "(free key at https://finnhub.io/)."
            )
        logger.info("Using FinnhubProvider (Free tier).")
        return FinnhubProvider()

    if selected == "web_scraper":
        logger.info("Using StockScraperProvider (HTTP scrape, no key).")
        return StockScraperProvider()

    if selected in {"ssi_vn", "ssi", "vn_ssi"}:
        logger.info("Using SSIVNProvider (SSI iBoard public API, HOSE/HNX/UPCOM).")
        return SSIVNProvider()

    if selected == "stooq":
        logger.info("Using StooqProvider (Stooq.com free CSV, 30+ years history).")
        return StooqProvider()

    if selected in {"yahoo_http", "yahoo"}:
        logger.info("Using YahooHttpProvider (direct v8 chart API, browser UA).")
        return YahooHttpProvider()

    raise DataSourceError(
        f"Unknown DATA_SOURCE='{selected}'. Supported: yfinance, yahoo_http, "
        "finnhub, alpha_vantage, web_scraper, ssi_vn, stooq, multi_source."
    )
