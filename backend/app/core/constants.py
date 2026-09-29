"""Shared constants for the Stock Lakehouse platform."""

from __future__ import annotations

# Diverse US stocks (real data from Yahoo Finance)
# Organized by sector for diverse portfolio demonstration

SUPPORTED_SYMBOLS: list[str] = [
    # Technology
    "AAPL",   # Apple - Consumer electronics
    "MSFT",   # Microsoft - Software & Cloud
    "GOOGL",  # Alphabet - Search & AI
    "META",   # Meta - Social media
    "NVDA",   # Nvidia - AI/GPU chips
    "AMD",    # AMD - Semiconductors
    "AVGO",   # Broadcom - Semiconductors
    "CRM",    # Salesforce - Software
    "ORCL",   # Oracle - Database
    "INTC",   # Intel - Semiconductors
    "QCOM",   # Qualcomm - Chips
    # Finance
    "JPM",    # JPMorgan - Banking
    "V",      # Visa - Payments
    "GS",     # Goldman Sachs - Investment
    "BAC",    # Bank of America
    "WFC",    # Wells Fargo
    "MA",     # Mastercard
    "BLK",    # BlackRock - Asset Management
    "AXP",    # American Express
    # Consumer
    "AMZN",   # Amazon - E-commerce & Cloud
    "TSLA",   # Tesla - EVs
    "WMT",    # Walmart - Retail
    "HD",     # Home Depot
    "NKE",    # Nike
    "SBUX",   # Starbucks
    "MCD",    # McDonald's
    "COST",   # Costco
    "TJX",    # TJX Companies
    # Healthcare
    "JNJ",    # Johnson & Johnson
    "UNH",    # UnitedHealth
    "PFE",    # Pfizer
    "ABBV",   # AbbVie
    "MRK",    # Merck
    "LLY",    # Eli Lilly
    "ABT",    # Abbott
    # Energy
    "XOM",    # Exxon Mobil
    "CVX",    # Chevron
    "COP",    # ConocoPhillips
    "SLB",    # Schlumberger
    "EOG",    # EOG Resources
    # Industrial
    "CAT",    # Caterpillar
    "BA",     # Boeing
    "GE",     # General Electric
    "HON",    # Honeywell
    "UPS",    # United Parcel Service
    # Crypto-related
    "COIN",   # Coinbase - Crypto exchange
    "MSTR",   # MicroStrategy - Bitcoin treasury
    # China Tech (ADRs)
    "BABA",   # Alibaba
    "BIDU",   # Baidu
    "JD",     # JD.com
    "PDD",    # PDD Holdings (Pinduoduo)
]

# Market Indexes (for benchmarking)
MARKET_INDEXES: list[str] = [
    "^GSPC",   # S&P 500
    "^DJI",    # Dow Jones
    "^IXIC",   # NASDAQ
]

# Crypto (via Yahoo Finance)
CRYPTO_SYMBOLS: list[str] = [
    "BTC-USD",  # Bitcoin
    "ETH-USD",  # Ethereum
]

# All available symbols
ALL_SYMBOLS: list[str] = SUPPORTED_SYMBOLS + MARKET_INDEXES + CRYPTO_SYMBOLS

# Intervals
SUPPORTED_INTERVALS: list[str] = ["1d", "1h", "15m", "5m"]

OHLCV_COLUMNS: list[str] = [
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "source",
    "ingestion_time",
]

BRONZE_PARTITION_COLUMNS: list[str] = ["symbol", "year", "month"]

GOLD_FEATURE_COLUMNS: list[str] = [
    "return",
    "log_return",
    "price_change",
    "volume_change",
    "sma_5",
    "sma_10",
    "sma_20",
    "sma_50",
    "ema_12",
    "ema_26",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_middle",
    "bb_upper",
    "bb_lower",
    "rolling_std_20",
    "rolling_min_20",
    "rolling_max_20",
    "volume_ma_20",
    "close_lag_1",
    "close_lag_2",
    "return_lag_1",
    "volume_lag_1",
]

GOLD_TARGET_COLUMNS: list[str] = [
    "target_close_next",
    "target_return_next",
    "target_direction_next",
]

LINEAR_REGRESSION_FEATURES: list[str] = [
    "close",
    "volume",
    "return",
    "sma_5",
    "sma_10",
    "sma_20",
    "sma_50",
    "ema_12",
    "ema_26",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_middle",
    "bb_upper",
    "bb_lower",
    "rolling_std_20",
    "close_lag_1",
    "close_lag_2",
    "return_lag_1",
    "volume_lag_1",
]

LSTM_FEATURE_COLUMNS: list[str] = [
    "close",
    "volume",
    "return",
    "sma_20",
    "ema_12",
    "rsi_14",
    "macd",
    "bb_middle",
    "rolling_std_20",
]

ACADEMIC_DISCLAIMER = (
    "Kết quả phân tích và dự báo chỉ phục vụ nghiên cứu học thuật, "
    "không phải khuyến nghị đầu tư và không cam kết lợi nhuận tương lai."
)

INTERVAL_TO_PANDAS_FREQ: dict[str, str] = {
    "1d": "B",
    "1h": "h",
    "15m": "15min",
    "5m": "5min",
}

INTERVAL_BARS_PER_YEAR: dict[str, int] = {
    "1d": 252,
    "1h": 252 * 6.5,
    "15m": 252 * 26,
    "5m": 252 * 78,
}
