"""Market data providers - real data only.

All providers in this package call live APIs (yfinance, Finnhub, Alpha Vantage)
or scrape public endpoints.  There is no synthetic/sample data fallback.
"""

from app.data_sources.alpha_vantage_provider import AlphaVantageProvider
from app.data_sources.base import StockDataProvider
from app.data_sources.enhanced_fundamental_provider import EnhancedFundamentalProvider
from app.data_sources.enhanced_news_sentiment_provider import EnhancedNewsSentimentProvider
from app.data_sources.factory import get_data_provider
from app.data_sources.finnhub_provider import FinnhubProvider
from app.data_sources.fundamental_provider import FundamentalDataProvider
from app.data_sources.macro_provider import MacroDataProvider
from app.data_sources.market_index_provider import MarketIndexProvider
from app.data_sources.multi_source import MultiSourceProvider
from app.data_sources.news_sentiment_provider import NewsSentimentProvider
from app.data_sources.orderbook_provider import OrderBookProvider
from app.data_sources.web_scraper_provider import StockScraperProvider
from app.data_sources.yfinance_provider import YFinanceProvider
from app.data_sources.yfinance_python_provider import YFinancePythonProvider

__all__ = [
    "StockDataProvider",
    "YFinanceProvider",
    "YFinancePythonProvider",
    "AlphaVantageProvider",
    "FinnhubProvider",
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