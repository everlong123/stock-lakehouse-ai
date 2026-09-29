"""
Data Source Adapters - Adapter Pattern for Stock Data Lakehouse

Each source implements the same interface:
- fetch_prices(ticker, start, end, interval)
- fetch_news(ticker)

This allows easy swapping of data sources without changing the pipeline.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import requests
import time
import logging
import os

logger = logging.getLogger(__name__)


class BaseDataAdapter(ABC):
    """Abstract base class for all data adapters"""
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this data source"""
        pass
    
    @abstractmethod
    def fetch_prices(
        self, 
        ticker: str, 
        start: Optional[str] = None, 
        end: Optional[str] = None, 
        interval: str = "1D"
    ) -> pd.DataFrame:
        """Fetch OHLCV price data"""
        pass
    
    @abstractmethod
    def fetch_news(self, ticker: str = None, limit: int = 20) -> pd.DataFrame:
        """Fetch news"""
        pass
    
    def health_check(self) -> bool:
        """Check if the source is accessible"""
        try:
            return self._check_connection()
        except Exception:
            return False
    
    def _check_connection(self) -> bool:
        """Override in subclass to check specific endpoints"""
        return True


class YahooFinanceDirectAdapter(BaseDataAdapter):
    """
    Adapter for Yahoo Finance - Direct API (no yfinance package needed)
    Works well for US stocks
    """
    
    BASE_URL = "https://query1.finance.yahoo.com"
    
    # Rate limiting
    _last_request = 0
    MIN_REQUEST_INTERVAL = 1.0  # seconds
    
    @property
    def source_name(self) -> str:
        return "yahoo_finance"
    
    def _rate_limit(self):
        """Simple rate limiting"""
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self.MIN_REQUEST_INTERVAL:
            time.sleep(self.MIN_REQUEST_INTERVAL - elapsed)
        self._last_request = time.time()
    
    def fetch_prices(
        self, 
        ticker: str, 
        start: Optional[str] = None, 
        end: Optional[str] = None, 
        interval: str = "1D"
    ) -> pd.DataFrame:
        """
        Fetch OHLCV from Yahoo Finance Direct API
        
        Args:
            ticker: Stock symbol (e.g., 'AAPL', 'MSFT')
            start: Start date 'YYYY-MM-DD'
            end: End date 'YYYY-MM-DD'
            interval: '1d', '1wk', '1mo'
        """
        self._rate_limit()
        
        # Default to 2 years if not specified
        if end is None:
            end = datetime.now().strftime('%Y-%m-%d')
        if start is None:
            start_dt = datetime.now() - timedelta(days=730)
            start = start_dt.strftime('%Y-%m-%d')
        
        # Map interval
        interval_map = {
            '1D': '1d',
            '1W': '1wk', 
            '1M': '1mo',
            '1d': '1d',
            '1wk': '1wk',
            '1mo': '1mo',
        }
        yf_interval = interval_map.get(interval, '1d')
        
        # Calculate range in days
        start_dt = datetime.strptime(start, '%Y-%m-%d')
        end_dt = datetime.strptime(end, '%Y-%m-%d')
        range_days = (end_dt - start_dt).days
        
        logger.info(f"Fetching {ticker} from {start} to {end} (interval={yf_interval})")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            url = f"{self.BASE_URL}/v8/finance/chart/{ticker.upper()}"
            params = {
                'interval': yf_interval,
                'period1': int(datetime.strptime(start, '%Y-%m-%d').timestamp()),
                'period2': int(datetime.strptime(end, '%Y-%m-%d').timestamp()),
            }
            
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            
            if resp.status_code == 429:
                logger.warning(f"Rate limited, waiting...")
                time.sleep(5)
                resp = requests.get(url, params=params, headers=headers, timeout=15)
            
            resp.raise_for_status()
            data = resp.json()
            
            result = data.get('chart', {}).get('result', [{}])[0]
            if not result:
                logger.warning(f"No result for {ticker}")
                return pd.DataFrame()
            
            timestamps = result.get('timestamp', [])
            quote = result.get('indicators', {}).get('quote', [{}])[0]
            adj_close = result.get('indicators', {}).get('adjclose', [{}])[0]
            
            if not timestamps:
                logger.warning(f"No timestamp data for {ticker}")
                return pd.DataFrame()
            
            df = pd.DataFrame({
                'date': pd.to_datetime(timestamps, unit='s'),
                'open': quote.get('open'),
                'high': quote.get('high'),
                'low': quote.get('low'),
                'close': quote.get('close'),
                'volume': quote.get('volume'),
            })
            
            if adj_close and adj_close.get('adjclose'):
                df['adj_close'] = adj_close.get('adjclose')
            else:
                df['adj_close'] = df['close']
            
            # Drop rows with NaN close
            df = df.dropna(subset=['close'])
            
            # Add metadata
            df['ticker'] = ticker.upper()
            df['source'] = self.source_name
            df['fetched_at'] = datetime.now().isoformat()
            
            logger.info(f"Got {len(df)} rows for {ticker}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching {ticker}: {e}")
            raise
    
    def fetch_news(self, ticker: str = None, limit: int = 20) -> pd.DataFrame:
        """
        Fetch news for a specific ticker from Yahoo Finance RSS
        
        Args:
            ticker: Stock symbol (e.g., 'AAPL', 'MSFT')
            limit: Maximum number of news items
        """
        if not ticker:
            logger.warning(f"Yahoo Finance news requires ticker")
            return pd.DataFrame()
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        try:
            # Yahoo Finance RSS Feed
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker.upper()}&region=US&lang=en-US"
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                logger.warning(f"Yahoo RSS returned {resp.status_code}")
                return pd.DataFrame()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'xml')
            items = soup.find_all('item')[:limit]
            
            records = []
            for item in items:
                title = item.find('title')
                link = item.find('link')
                desc = item.find('description')
                pub_date = item.find('pubDate')
                
                records.append({
                    'ticker': ticker.upper(),
                    'title': title.text if title else '',
                    'link': link.text if link else '',
                    'published_at': pub_date.text if pub_date else '',
                    'description': desc.text if desc else '',
                    'source': self.source_name,
                    'fetched_at': datetime.now().isoformat()
                })
            
            df = pd.DataFrame(records)
            logger.info(f"Got {len(df)} news items for {ticker}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching Yahoo news for {ticker}: {e}")
            return pd.DataFrame()
    
    def _check_connection(self) -> bool:
        """Check Yahoo Finance API"""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/v8/finance/chart/AAPL",
                params={'interval': '1d', 'range': '5d'},
                timeout=10
            )
            return resp.status_code == 200
        except:
            return False


class VnExpressRSSAdapter(BaseDataAdapter):
    """Adapter for VnExpress RSS feed - Vietnamese business news"""
    
    RSS_URL = "https://vnexpress.net/rss/kinh-doanh.rss"
    
    @property
    def source_name(self) -> str:
        return "vnexpress_rss"
    
    def fetch_prices(self, ticker: str = None, start: str = None, end: str = None, interval: str = "1D") -> pd.DataFrame:
        """RSS adapter does not provide price data"""
        return pd.DataFrame()
    
    def fetch_news(self, ticker: str = None, limit: int = 20, keywords: list = None) -> pd.DataFrame:
        """
        Fetch news from VnExpress RSS with optional keyword filtering
        
        Args:
            ticker: Stock ticker to filter news
            limit: Maximum number of news items
            keywords: Additional keywords to filter news (e.g., ['Apple', 'iPhone'])
        """
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Build filter keywords
        filter_keywords = set()
        if ticker:
            # Add ticker as keyword
            filter_keywords.add(ticker.upper())
            # Add common ticker variations
            if ticker.upper() == 'AAPL':
                filter_keywords.update(['Apple', 'iPhone', 'Tim Cook', 'MacBook'])
            elif ticker.upper() == 'MSFT':
                filter_keywords.update(['Microsoft', 'Windows', 'Azure', 'Satya'])
            elif ticker.upper() == 'GOOGL':
                filter_keywords.update(['Google', 'Alphabet', 'Android', 'Gemini'])
            elif ticker.upper() == 'AMZN':
                filter_keywords.update(['Amazon', 'AWS', 'Jeff Bezos'])
            elif ticker.upper() == 'TSLA':
                filter_keywords.update(['Tesla', 'Elon Musk', 'EV', 'Electric'])
            elif ticker.upper() == 'META':
                filter_keywords.update(['Meta', 'Facebook', 'Zuckerberg', 'Instagram'])
            elif ticker.upper() == 'NVDA':
                filter_keywords.update(['Nvidia', 'GPU', 'AI', 'Jensen Huang'])
            elif ticker.upper() == 'FPT':
                filter_keywords.update(['FPT', 'Công nghệ'])
            elif ticker.upper() == 'VNM':
                filter_keywords.update(['Vinamilk', 'Sữa'])
            elif ticker.upper() == 'VIC':
                filter_keywords.update(['Vingroup', 'VinFast'])
            elif ticker.upper() == 'VPB':
                filter_keywords.update(['VPBank', 'Việt Nam Phú'])
            elif ticker.upper() == 'TCB':
                filter_keywords.update(['Techcombank', 'Techcom'])
            elif ticker.upper() == 'ACB':
                filter_keywords.update(['ACB', 'Á Châu'])
        
        # Add custom keywords
        if keywords:
            filter_keywords.update([k.upper() for k in keywords])
        
        try:
            resp = requests.get(self.RSS_URL, headers=headers, timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'xml')
            items = soup.find_all('item')[:limit * 3]  # Fetch more to filter
            
            records = []
            for item in items:
                if len(records) >= limit:
                    break
                    
                title = item.find('title')
                link = item.find('link')
                pub_date = item.find('pubDate')
                desc = item.find('description')
                
                title_text = title.text if title else ''
                desc_text = ''
                if desc:
                    from bs4 import BeautifulSoup as BS
                    clean = BS(desc.text, 'html.parser').get_text()
                    desc_text = clean[:500]
                
                # Combine text for searching
                search_text = (title_text + ' ' + desc_text).upper()
                
                # Filter by keywords if keywords specified
                if filter_keywords:
                    # Check if any keyword is in the news
                    matched = False
                    for keyword in filter_keywords:
                        if keyword.upper() in search_text:
                            matched = True
                            break
                    
                    if not matched:
                        # Still include some general business news (no keyword filter)
                        # Only if no specific filter required
                        pass
                
                records.append({
                    'ticker': ticker.upper() if ticker else 'MARKET',
                    'title': title_text,
                    'link': link.text if link else '',
                    'published_at': pub_date.text if pub_date else '',
                    'description': desc_text,
                    'source': self.source_name,
                    'fetched_at': datetime.now().isoformat(),
                    'keywords_matched': list(filter_keywords) if filter_keywords else []
                })
            
            df = pd.DataFrame(records)
            
            # Sort: matched keywords first, then by date
            if 'keywords_matched' in df.columns and len(df) > 0:
                df['has_keywords'] = df['keywords_matched'].apply(lambda x: len(x) > 0)
                df = df.sort_values('has_keywords', ascending=False)
                df = df.drop('has_keywords', axis=1)
            
            logger.info(f"Got {len(df)} news items from VnExpress" + (f" for {ticker}" if ticker else ""))
            return df.head(limit)
            
        except Exception as e:
            logger.error(f"Error fetching RSS: {e}")
            return pd.DataFrame()
    
    def _check_connection(self) -> bool:
        """Check VnExpress RSS"""
        try:
            resp = requests.get(self.RSS_URL, timeout=10)
            return resp.status_code == 200
        except:
            return False


class DataSourceFactory:
    """Factory to create data adapters"""
    
    _adapters = {
        'yahoo': YahooFinanceDirectAdapter,
        'vnexpress': VnExpressRSSAdapter,
    }
    
    @classmethod
    def create(cls, source: str) -> BaseDataAdapter:
        """Create an adapter by name"""
        adapter_class = cls._adapters.get(source.lower())
        if not adapter_class:
            raise ValueError(f"Unknown source: {source}. Available: {list(cls._adapters.keys())}")
        return adapter_class()
    
    @classmethod
    def list_sources(cls) -> list:
        """List available sources"""
        return list(cls._adapters.keys())
    
    @classmethod
    def register(cls, name: str, adapter_class: type):
        """Register a new adapter"""
        cls._adapters[name.lower()] = adapter_class


class MultiSourceAdapter:
    """Wrapper to use multiple sources with fallback"""
    
    def __init__(self, sources: list[str]):
        self.adapters = []
        for source in sources:
            try:
                adapter = DataSourceFactory.create(source)
                self.adapters.append(adapter)
                logger.info(f"Loaded adapter: {adapter.source_name}")
            except Exception as e:
                logger.warning(f"Failed to load {source}: {e}")
    
    def fetch_prices(self, ticker: str, **kwargs) -> pd.DataFrame:
        """Try each adapter until one works"""
        for adapter in self.adapters:
            try:
                df = adapter.fetch_prices(ticker, **kwargs)
                if not df.empty:
                    logger.info(f"Got prices from {adapter.source_name}")
                    return df
            except Exception as e:
                logger.warning(f"{adapter.source_name} failed: {e}")
        
        logger.error(f"All adapters failed for {ticker}")
        return pd.DataFrame()
    
    def fetch_news(self, ticker: str = None, **kwargs) -> pd.DataFrame:
        """Aggregate news from all adapters"""
        all_news = []
        for adapter in self.adapters:
            try:
                df = adapter.fetch_news(ticker, **kwargs)
                if not df.empty:
                    all_news.append(df)
                    logger.info(f"Got news from {adapter.source_name}")
            except Exception as e:
                logger.warning(f"{adapter.source_name} news failed: {e}")
        
        if all_news:
            return pd.concat(all_news, ignore_index=True)
        return pd.DataFrame()
    
    def health_check(self) -> dict:
        """Check status of all adapters"""
        status = {}
        for adapter in self.adapters:
            status[adapter.source_name] = adapter.health_check()
        return status
