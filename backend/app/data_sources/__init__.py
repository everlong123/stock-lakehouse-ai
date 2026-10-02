"""Market data providers — real data only.

All providers call live APIs (yfinance, Finnhub, Alpha Vantage, SSI iBoard)
or scrape public endpoints.  No synthetic/sample data fallback.
"""

from app.data_sources.alpha_vantage_provider import AlphaVantageProvider
from app.data_sources.base import StockDataProvider
from app.data_sources.enhanced_fundamental_provider import EnhancedFundamentalProvider
from app.data_sources.enhanced_news_sentiment_provider import EnhancedNewsSentimentProvider
from app.data_sources.factory import get_data_provider
from app.data_sources.finnhub_provider import FinnhubProvider
from app.data_sources.macro_provider import MacroDataProvider
from app.data_sources.market_index_provider import MarketIndexProvider
from app.data_sources.multi_source import MultiSourceProvider
from app.data_sources.orderbook_provider import OrderBookProvider
from app.data_sources.ssi_vn_provider import SSIVNProvider
from app.data_sources.web_scraper_provider import StockScraperProvider
from app.data_sources.yfinance_python_provider import YFinancePythonProvider

# Aliases for backward compatibility
FundamentalDataProvider = EnhancedFundamentalProvider
NewsSentimentProvider = EnhancedNewsSentimentProvider

__all__ = [
    "StockDataProvider",
    "YFinancePythonProvider",
    "AlphaVantageProvider",
    "FinnhubProvider",
    "SSIVNProvider",
    "StockScraperProvider",
    "FundamentalDataProvider",
    "EnhancedFundamentalProvider",
    "NewsSentimentProvider",
    "EnhancedNewsSentimentProvider",
    "MacroDataProvider",
    "MarketIndexProvider",
    "OrderBookProvider",
    "MultiSourceProvider",
    "get_data_provider",
]
