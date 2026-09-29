"""Data Adapters for Stock Lakehouse"""

from .base import (
    BaseDataAdapter,
    YahooFinanceDirectAdapter,
    VnExpressRSSAdapter,
    DataSourceFactory,
    MultiSourceAdapter,
)

# Aliases for convenience
YahooFinanceAdapter = YahooFinanceDirectAdapter

__all__ = [
    'BaseDataAdapter',
    'YahooFinanceAdapter',
    'YahooFinanceDirectAdapter',
    'VnExpressRSSAdapter',
    'DataSourceFactory',
    'MultiSourceAdapter',
]
