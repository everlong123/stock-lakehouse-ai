"""Enhanced News and Sentiment provider with NLP processing."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class EnhancedSentimentAnalyzer:
    """
    Enhanced sentiment analyzer with:
    - Vietnamese financial lexicon
    - Rule-based sentiment modifiers
    - Entity extraction
    - Headline/body weight
    """

    # Strong positive words
    POSITIVE_STRONG = {
        "tăng trưởng", "lợi nhuận", "lãi", "tích cực", "khởi sắc", "bứt phá",
        "lạc quan", "hưởng lợi", "vượt kỳ vọng", "kỷ lục", "thắng lớn",
        "lợi nhuận tăng", "doanh thu tăng", "cổ tức cao", "tăng giá mạnh",
        "breakout", "outperform", "buy rating", "upgrade", "strong buy",
    }

    # Positive words
    POSITIVE = {
        "tăng", "cổ tức", "vượt", "lên", "cải thiện", "mở rộng",
        "đầu tư", "hợp tác", "ký kết", "triển vọng", "khả quan",
        "tốt", "đà", "hồi phục", "ổn định", "tích cực",
        "rise", "profit", "growth", "positive", "bullish", "gain", "up",
    }

    # Strong negative words
    NEGATIVE_STRONG = {
        "thua lỗ", "lỗ lớn", "lao dốc", "phá sản", "bị điều tra",
        "bị kiểm tra", "vi phạm", "xử phạt", "cảnh báo", "rủi ro cao",
        "mất khả năng", "giải thể", "phá đổ", "thua kiện",
        "bankruptcy", "fraud", "investigation", "downgrade", "strong sell",
    }

    # Negative words
    NEGATIVE = {
        "giảm", "lỗ", "tiêu cực", "trì trệ", "sụt giảm",
        "rủi ro", "bất lợi", "xuống", "giáng", "yếu",
        "khó khăn", "thận trọng", "giảm giá", "bán ra",
        "fall", "loss", "decline", "negative", "bearish", "drop",
    }

    # Intensifiers
    INTENSIFIERS = {
        "rất": 1.5, "cực kỳ": 2.0, "quá": 1.3, "vô cùng": 1.8,
        "highly": 1.5, "extremely": 2.0, "very": 1.3,
    }

    # Negators
    NEGATORS = {
        "không", "chưa", "chẳng", " không", "không có",
        "not", "no", "never", "neither",
    }

    def analyze(self, text: str, title_weight: float = 1.5) -> dict[str, Any]:
        """
        Analyze sentiment of text with Vietnamese financial context.

        Args:
            text: Combined title and body text
            title: Headline (weighted more heavily)
            body: Article body
            title_weight: Weight multiplier for title sentiment

        Returns:
            Dictionary with sentiment scores and metadata
        """
        if not text:
            return self._empty_result()

        text_lower = text.lower()
        words = self._tokenize(text_lower)

        # Score calculation
        positive_count = 0
        negative_count = 0
        strong_positive = 0
        strong_negative = 0

        i = 0
        while i < len(words):
            # Check for multi-word phrases
            phrase = " ".join(words[i:i+3])
            phrase_2 = " ".join(words[i:i+2])

            # Check strong positive phrases
            if phrase in self.POSITIVE_STRONG or phrase_2 in self.POSITIVE_STRONG:
                strong_positive += 1
                i += 3 if phrase in self.POSITIVE_STRONG else 2
                continue

            # Check strong negative phrases
            if phrase in self.NEGATIVE_STRONG or phrase_2 in self.NEGATIVE_STRONG:
                strong_negative += 1
                i += 3 if phrase in self.NEGATIVE_STRONG else 2
                continue

            # Check single word
            word = words[i]
            if word in self.POSITIVE_STRONG or word in self.POSITIVE:
                positive_count += 1
            elif word in self.NEGATIVE_STRONG or word in self.NEGATIVE:
                negative_count += 1

            i += 1

        # Calculate base sentiment
        total = strong_positive + strong_negative + positive_count + negative_count
        if total == 0:
            sentiment = 0.0
        else:
            sentiment = (strong_positive * 2 + positive_count - strong_negative * 2 - negative_count) / total

        # Apply intensifiers/negators
        sentiment = self._apply_modifiers(text_lower, sentiment)

        # Clamp to [-1, 1]
        sentiment = max(-1.0, min(1.0, sentiment))

        # Confidence based on number of signals
        confidence = min(1.0, total / 5)

        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "positive_signals": positive_count + strong_positive,
            "negative_signals": negative_count + strong_negative,
            "strong_positive": strong_positive,
            "strong_negative": strong_negative,
            "sentiment_label": self._label(sentiment),
            "keywords": self._extract_keywords(text),
        }

    def _tokenize(self, text: str) -> list[str]:
        """Simple Vietnamese tokenization."""
        # Remove punctuation and split
        text = re.sub(r'[^\w\s]', ' ', text)
        return text.split()

    def _apply_modifiers(self, text: str, sentiment: float) -> float:
        """Apply intensifiers and negators."""
        modifier = 1.0

        # Check for negators
        for neg in self.NEGATORS:
            if neg in text:
                modifier *= -0.8
                break

        # Check for intensifiers
        for intensifier, multiplier in self.INTENSIFIERS.items():
            if intensifier in text:
                modifier *= multiplier
                break

        return sentiment * modifier

    def _label(self, sentiment: float) -> str:
        """Convert sentiment score to label."""
        if sentiment >= 0.3:
            return "positive"
        elif sentiment <= -0.3:
            return "negative"
        else:
            return "neutral"

    def _extract_keywords(self, text: str, top_n: int = 5) -> list[str]:
        """Extract top keywords from text."""
        words = self._tokenize(text.lower())

        # Remove stopwords
        stopwords = {
            "và", "của", "là", "có", "được", "trong", "cho", "với",
            "theo", "tại", "đã", "sẽ", "để", "từ", "này", "các",
            "and", "the", "is", "are", "was", "were", "be", "to", "of",
        }
        words = [w for w in words if w not in stopwords and len(w) > 2]

        # Return top by frequency
        counter = Counter(words)
        return [word for word, _ in counter.most_common(top_n)]

    def _empty_result(self) -> dict[str, Any]:
        return {
            "sentiment": 0.0,
            "confidence": 0.0,
            "positive_signals": 0,
            "negative_signals": 0,
            "strong_positive": 0,
            "strong_negative": 0,
            "sentiment_label": "neutral",
            "keywords": [],
        }


class EnhancedNewsSentimentProvider:
    """Enhanced news provider with NLP-based sentiment analysis.
    
    Sources: Yahoo Finance RSS (stock-specific) + VnExpress RSS (VN business)
    """

    source_name = "news_sentiment_nlp"

    NEWS_SOURCES = [
        "finance.yahoo.com",
        "vnexpress.net",
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.analyzer = EnhancedSentimentAnalyzer()

    def get_news_for_symbol(self, symbol: str, limit: int = 20) -> pd.DataFrame:
        """Get news articles for a symbol with sentiment analysis."""
        symbol = symbol.upper()
        articles = []

        # Search multiple sources
        articles.extend(self._search_cafef_news(symbol, limit))
        articles.extend(self._search_vietstock_news(symbol, limit // 2))

        if not articles:
            logger.warning(f"No news found for {symbol}")
            return pd.DataFrame()

        # Analyze sentiment for each article
        for article in articles:
            combined_text = f"{article.get('title', '')} {article.get('content', '')}"
            sentiment_result = self.analyzer.analyze(combined_text)
            article["sentiment"] = sentiment_result["sentiment"]
            article["sentiment_confidence"] = sentiment_result["confidence"]
            article["sentiment_label"] = sentiment_result["sentiment_label"]
            article["sentiment_keywords"] = ",".join(sentiment_result["keywords"])

        frame = pd.DataFrame(articles)
        frame["source"] = self.source_name
        frame["ingestion_time"] = pd.Timestamp.now(tz="UTC")

        return frame

    def _search_cafef_news(self, symbol: str, limit: int) -> list[dict]:
        """Search Yahoo Finance RSS for news (replaces CafeF)."""
        return self._search_yahoo_news(symbol, limit)

    def _search_yahoo_news(self, symbol: str, limit: int) -> list[dict]:
        """Search Yahoo Finance RSS for news."""
        articles = []

        try:
            # Yahoo Finance RSS Feed
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
            response = self.session.get(url, timeout=10)
            
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "xml")
            items = soup.find_all("item")[:limit]

            for item in items:
                try:
                    title = item.find("title")
                    link = item.find("link")
                    desc = item.find("description")
                    pub_date = item.find("pubDate")

                    articles.append({
                        "symbol": symbol,
                        "title": title.text if title else "",
                        "content": desc.text if desc else "",
                        "url": link.text if link else "",
                        "published_date": self._parse_date(pub_date.text if pub_date else ""),
                        "source": "yahoo_finance",
                    })
                except Exception:
                    continue

        except Exception as exc:
            logger.warning(f"Yahoo news search failed for {symbol}: {exc}")

        return articles[:limit]

    def _search_vietstock_news(self, symbol: str, limit: int) -> list[dict]:
        """Search VnExpress RSS for VN business news (replaces VietStock)."""
        return self._search_vnexpress_news(symbol, limit)

    def _search_vnexpress_news(self, symbol: str, limit: int) -> list[dict]:
        """Search VnExpress RSS for VN business news."""
        articles = []

        try:
            # VnExpress RSS Feed
            url = "https://vnexpress.net/rss/kinh-doanh.rss"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.text, "xml")
            items = soup.find_all("item")[:limit * 2]

            # Filter keywords based on symbol
            filter_keywords = self._get_symbol_keywords(symbol)

            for item in items:
                if len(articles) >= limit:
                    break
                    
                try:
                    title = item.find("title")
                    link = item.find("link")
                    desc = item.find("description")
                    pub_date = item.find("pubDate")

                    title_text = title.text if title else ""
                    desc_text = ""
                    if desc:
                        clean = BeautifulSoup(desc.text, "html.parser").get_text()
                        desc_text = clean[:500]

                    # Check if news is relevant to symbol
                    if filter_keywords:
                        search_text = (title_text + " " + desc_text).upper()
                        is_relevant = any(kw.upper() in search_text for kw in filter_keywords)
                        # Include some general news too
                        if not is_relevant and len(articles) >= limit // 2:
                            continue

                    articles.append({
                        "symbol": symbol,
                        "title": title_text,
                        "content": desc_text,
                        "url": link.text if link else "",
                        "published_date": self._parse_date(pub_date.text if pub_date else ""),
                        "source": "vnexpress",
                    })
                except Exception:
                    continue

        except Exception as exc:
            logger.warning(f"VnExpress news search failed: {exc}")

        return articles[:limit]

    def _get_symbol_keywords(self, symbol: str) -> list[str]:
        """Get keywords for symbol to filter relevant news."""
        keywords_map = {
            "AAPL": ["Apple", "iPhone", "Tim Cook", "MacBook", "iOS"],
            "MSFT": ["Microsoft", "Windows", "Azure", "Satya"],
            "GOOGL": ["Google", "Alphabet", "Android", "Gemini"],
            "META": ["Meta", "Facebook", "Zuckerberg", "Instagram"],
            "NVDA": ["Nvidia", "GPU", "AI", "Jensen Huang"],
            "TSLA": ["Tesla", "Elon Musk", "EV", "Electric"],
            "AMZN": ["Amazon", "AWS", "E-commerce"],
            "AMD": ["AMD", "Ryzen", "Lisa Su"],
            "JPM": ["JPMorgan", "Jamie Dimon", "Banking"],
            "V": ["Visa", "Payments"],
            "GS": ["Goldman Sachs", "Investment Banking"],
            "WMT": ["Walmart", "Retail"],
            "JNJ": ["Johnson & Johnson", "Healthcare", "Pharma"],
            "UNH": ["UnitedHealth", "Health Insurance"],
            "XOM": ["Exxon", "Oil", "Energy"],
            "CVX": ["Chevron", "Oil", "Energy"],
            "COIN": ["Coinbase", "Crypto", "Bitcoin"],
            "FPT": ["FPT", "Công nghệ"],
            "VNM": ["Vinamilk", "Sữa"],
        }
        return keywords_map.get(symbol.upper(), [])

    def _fetch_article_content(self, url: str) -> str:
        """Fetch full article content."""
        if not url:
            return ""

        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                return ""

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.decompose()

            # Find article content
            content_elem = soup.find("div", {"class": "content"}) or \
                          soup.find("article") or \
                          soup.find("div", {"id": "content"})

            if content_elem:
                return content_elem.get_text(strip=True)[:2000]  # Limit content length

        except Exception:
            pass

        return ""

    def get_market_news(self, limit: int = 30) -> pd.DataFrame:
        """Get general market news from Yahoo Finance and VnExpress."""
        articles = []

        # Yahoo Finance market news
        try:
            # S&P 500 market news
            url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSP&region=US&lang=en-US"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "xml")
                items = soup.find_all("item")[:limit]
                
                for item in items:
                    try:
                        title = item.find("title")
                        link = item.find("link")
                        desc = item.find("description")
                        pub_date = item.find("pubDate")
                        
                        articles.append({
                            "symbol": None,
                            "title": title.text if title else "",
                            "content": desc.text if desc else "",
                            "url": link.text if link else "",
                            "published_date": self._parse_date(pub_date.text if pub_date else ""),
                            "source": "yahoo_finance",
                        })
                    except Exception:
                        continue
        except Exception as exc:
            logger.warning(f"Yahoo market news fetch failed: {exc}")

        # VnExpress business news
        try:
            url = "https://vnexpress.net/rss/kinh-doanh.rss"
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "xml")
                items = soup.find_all("item")[:limit // 2]
                
                for item in items:
                    try:
                        title = item.find("title")
                        link = item.find("link")
                        desc = item.find("description")
                        pub_date = item.find("pubDate")
                        
                        articles.append({
                            "symbol": None,
                            "title": title.text if title else "",
                            "content": BeautifulSoup(desc.text, "html.parser").get_text()[:500] if desc else "",
                            "url": link.text if link else "",
                            "published_date": self._parse_date(pub_date.text if pub_date else ""),
                            "source": "vnexpress",
                        })
                    except Exception:
                        continue
        except Exception as exc:
            logger.warning(f"VnExpress market news fetch failed: {exc}")

        # Analyze sentiment
        for article in articles:
            sentiment = self.analyzer.analyze(article.get("title", ""))
            article["sentiment"] = sentiment["sentiment"]
            article["sentiment_label"] = sentiment["sentiment_label"]

        frame = pd.DataFrame(articles)
        if not frame.empty:
            frame["source"] = self.source_name
            frame["ingestion_time"] = pd.Timestamp.now(tz="UTC")

        return frame

    def get_sentiment_summary(self, symbol: str, days: int = 7) -> dict[str, Any]:
        """Get aggregated sentiment summary."""
        news = self.get_news_for_symbol(symbol, limit=50)

        if news.empty:
            return {
                "symbol": symbol,
                "total_articles": 0,
                "avg_sentiment": 0.0,
                "avg_confidence": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "trend": "neutral",
                "top_keywords": [],
            }

        # Filter to recent days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        news["published_date"] = pd.to_datetime(news["published_date"], utc=True)
        news = news[news["published_date"] >= cutoff]

        if news.empty:
            return {
                "symbol": symbol,
                "total_articles": 0,
                "avg_sentiment": 0.0,
                "trend": "neutral",
            }

        avg_sentiment = news["sentiment"].mean()
        avg_confidence = news["sentiment_confidence"].mean()
        positive = len(news[news["sentiment"] > 0.2])
        negative = len(news[news["sentiment"] < -0.2])
        neutral = len(news) - positive - negative

        # Get all keywords
        all_keywords = []
        for kw_str in news.get("sentiment_keywords", []):
            if kw_str:
                all_keywords.extend(kw_str.split(","))
        keyword_counts = Counter(all_keywords)
        top_keywords = [k for k, _ in keyword_counts.most_common(10)]

        if avg_sentiment > 0.2:
            trend = "positive"
        elif avg_sentiment < -0.2:
            trend = "negative"
        else:
            trend = "neutral"

        return {
            "symbol": symbol,
            "total_articles": len(news),
            "avg_sentiment": float(avg_sentiment),
            "avg_confidence": float(avg_confidence),
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "trend": trend,
            "top_keywords": top_keywords,
            "period_days": days,
        }

    def get_sentiment_timeseries(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """Get sentiment data over time."""
        news = self.get_news_for_symbol(symbol, limit=100)

        if news.empty:
            return pd.DataFrame()

        # Filter to period
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        news["published_date"] = pd.to_datetime(news["published_date"], utc=True)
        news = news[news["published_date"] >= cutoff]

        if news.empty:
            return pd.DataFrame()

        # Group by date
        news["date"] = news["published_date"].dt.date
        daily = news.groupby("date").agg({
            "sentiment": "mean",
            "sentiment_confidence": "mean",
            "title": "count",
        }).rename(columns={"title": "article_count"})

        daily = daily.reset_index()
        daily["date"] = pd.to_datetime(daily["date"])
        daily["symbol"] = symbol
        daily["source"] = self.source_name

        return daily

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse Vietnamese date string."""
        if not date_str:
            return datetime.now(timezone.utc)

        formats = [
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return datetime.now(timezone.utc)
