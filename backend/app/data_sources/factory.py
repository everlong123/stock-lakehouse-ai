"""Factory for the configured market data provider.

All providers return **real market data** only - there is no offline/synthetic
fallback.  When ``DATA_SOURCE`` is unset or invalid the factory falls back to
``yfinance`` (the official Python package), which is free, key-less and
returns > 10 years of OHLCV history for every supported US ticker.

Supported ``DATA_SOURCE`` values:

- ``yfinance``       -> :class:`YFinancePythonProvider` (official ``yfinance`` package).
- ``yfinance_direct``-> :class:`YFinanceProvider` (raw HTTP, no extra dependency).
- ``finnhub``        -> :class:`FinnhubProvider` (Free tier, 60 req/min).
- ``alpha_vantage``  -> :class:`AlphaVantageProvider` (Free tier, key required).
- ``web_scraper``    -> :class:`StockScraperProvider` (HTTP scrape, no key).
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
from app.data_sources.web_scraper_provider import StockScraperProvider
from app.data_sources.yfinance_provider import YFinanceProvider
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
            "ONLY real market data. Use one of: yfinance, yfinance_direct, "
            "finnhub, alpha_vantage, web_scraper, multi_source."
        )

    if selected == "multi_source":
        logger.info("Using MultiSourceProvider (failover chain of real APIs).")
        return MultiSourceProvider()

    if selected == "yfinance":
        try:
            return YFinancePythonProvider()
        except Exception as exc:
            logger.warning(
                "yfinance package unavailable (%s); falling back to direct REST client.",
                exc,
            )
            return YFinanceProvider()

    if selected == "yfinance_direct":
        logger.info("Using YFinanceProvider (raw HTTP, no yfinance package required).")
        return YFinanceProvider()

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

    raise DataSourceError(
        f"Unknown DATA_SOURCE='{selected}'. Supported: yfinance, yfinance_direct, "
        "finnhub, alpha_vantage, web_scraper, multi_source."
    )