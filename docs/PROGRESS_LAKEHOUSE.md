# Báo cáo tiến độ – Tầng Data Lakehouse & Dữ liệu

> **Giai đoạn:** Tuần 1 – Tuần 2 (hoàn thành) | **Báo cáo cho:** Thầy
> **Đề tài:** Xây dựng hệ thống phân tích và dự báo chứng khoán dựa trên Data Lakehouse kết hợp AI Agent

---

## 0. Index nhanh – File nào làm gì (đọc trước khi vào chi tiết)

Toàn bộ code nằm trong `backend/app/`. Đây là bản đồ cho người mới:

| Thư mục / file | Nhiệm vụ chính |
|---|---|
| `app/core/config.py` | Đọc `.env`, expose singleton `settings` |
| `app/core/constants.py` | Danh sách 53 mã VN + 60 mã US, schema OHLCV, tên cột feature |
| `app/core/exceptions.py` | Các exception nghiệp vụ (`DataSourceError`, `StorageError`, ...) |
| `app/data_sources/base.py` | Abstract `StockDataProvider` (3 method bắt buộc) |
| `app/data_sources/factory.py` | `get_data_provider()` — chọn provider theo biến môi trường |
| `app/data_sources/multi_source.py` | Failover chain — thay thế khi 1 nguồn lỗi |
| `app/data_sources/yfinance_python_provider.py` | Lấy OHLCV US qua thư viện `yfinance` (provider chính) |
| `app/data_sources/finnhub_provider.py` | Finnhub REST (cần `FINNHUB_API_KEY`) |
| `app/data_sources/alpha_vantage_provider.py` | Alpha Vantage REST (cần `ALPHA_VANTAGE_API_KEY`) |
| `app/data_sources/ssi_vn_provider.py` | SSI iBoard public API — 53 mã VN |
| `app/data_sources/web_scraper_provider.py` | CafeF scrape + Yahoo HTTP fallback |
| `app/lakehouse/storage_base.py` | Abstract `StorageBackend` (MinIO hoặc local) |
| `app/lakehouse/storage_factory.py` | `get_storage_backend()` — fallback khi MinIO chết |
| `app/lakehouse/local_storage.py` | Ghi Parquet xuống `backend/data/` |
| `app/lakehouse/minio_storage.py` | Ghi Parquet lên bucket MinIO |
| `app/lakehouse/parquet_manager.py` | Sinh đường dẫn Hive-style `symbol=AAPL/year=2026/month=09/` |
| `app/lakehouse/bronze.py` | Class `BronzeLayer` — raw, append-only, dedupe |
| `app/lakehouse/silver.py` | Class `SilverLayer` — làm sạch, validate OHLC, ghi `_errors/` |
| `app/lakehouse/gold.py` | Class `GoldLayer` — gọi feature engineering |
| `app/lakehouse/gold_features.py` | `GoldFeaturesLayer` cho sentiment/macro/index (phụ) |
| `app/lakehouse/news_silver.py` | `NewsSilverLayer` — schema riêng cho tin tức |
| `app/lakehouse/fundamentals_silver.py` | `FundamentalsSilverLayer` — chỉ số tài chính |
| `app/lakehouse/iceberg_manager.py` | Apache Iceberg — time travel, schema evolution |
| `app/lakehouse/spark_session.py` | Lazy Spark session (chỉ bật khi `USE_SPARK=true`) |
| `app/lakehouse/pipeline.py` | `LakehousePipeline` — orchestrator Bronze→Silver→Gold |
| `app/lakehouse/__init__.py` | Re-export để gọi gọn từ ngoài |
| `app/features/feature_engineering.py` | `build_gold_features()` — strip cột, tính idempotent |
| `app/features/technical_features.py` | Wrapper gọi 5 indicator cơ bản |
| `app/features/price_features.py` | Return, log return, lag, rolling 20 |
| `app/features/target_features.py` | `target_close_next`, `target_direction_next` (shift -1) |
| `app/features/advanced_features.py` | Stochastic, ATR, ADX, Supertrend, Ichimoku, … |
| `app/features/macro_features.py` | Regime bull/bear + macro placeholder |
| `app/indicators/service.py` | `add_indicators()` — orchestration của 5 indicator |
| `app/indicators/sma.py` | Simple Moving Average |
| `app/indicators/ema.py` | Exponential Moving Average |
| `app/indicators/rsi.py` | RSI Wilder smoothing |
| `app/indicators/macd.py` | MACD line + signal + histogram |
| `app/indicators/bollinger.py` | Bollinger upper/middle/lower |
| `app/pipelines/orchestrator.py` | **SINGLE ENTRY POINT** — gộp 7 file cũ. Chứa: `ingest_symbol`, `validate_ohlc_frame`, `transform_to_silver`, `build_quality_report`, `assert_quality_passed`, `build_gold_layer`, `run_symbol_pipeline` |
| `docker-compose.yml` | 4 service Docker: MySQL, MinIO, Iceberg REST, Kafka |
| `.env` | Config runtime: `DATA_SOURCE`, `STORAGE_BACKEND`, API key |

---

---

## Mục lục

1. [Tổng quan những gì em đã làm](#1-tổng-quan-những-gì-em-đã-làm)
2. [Kiến trúc tổng thể hệ thống](#2-kiến-trúc-tổng-thể-hệ-thống)
3. [Tầng Bronze – Nơi dữ liệu gốc được giữ nguyên](#3-tầng-bronze--nơi-dữ-liệu-gốc-được-giữ-nguyên)
4. [Tầng Silver – Làm sạch có kiểm soát](#4-tầng-silver--làm-sạch-có-kiểm-soát)
5. [Tầng Gold – Feature engineering sẵn sàng cho ML/DL](#5-tầng-gold--feature-engineering-sẵn-sàng-cho-mldl)
6. [Pipeline điều phối luồng Bronze → Silver → Gold](#6-pipeline-điều-phối-luồng-bronze--silver--gold)
7. [Nguồn dữ liệu và cơ chế failover](#7-nguồn-dữ-liệu-và-cơ-chế-failover)
8. [Tầng lưu trữ – Tại sao tách Storage Backend?](#8-tầng-lưu-trữ--tại-sao-tách-storage-backend)
9. [Apache Iceberg – Vì sao chọn Iceberg thay vì Delta Lake?](#9-apache-iceberg--vì-sao-chọn-iceberg-thay-vì-delta-lake)
10. [Khó khăn đã gặp và cách xử lý](#10-khó-khăn-đã-gặp-và-cách-xử-lý)
11. [Phần chưa hoàn thành và kế hoạch tuần 3–4](#11-phần-chưa-hoàn-thành-và-kế-hoạch-tuần-3-4)
12. [Hướng dẫn demo cho thầy](#12-hướng-dẫn-demo-cho-thầy)
13. [Các câu hỏi dự đoán và câu trả lời](#13-các-câu-hỏi-dự-đoán-và-câu-trả-lời)

---

## 1. Tổng quan những gì em đã làm

Sau 2 tuần đầu, em tập trung xây **tầng nền tảng dữ liệu** trước vì một nguyên tắc cơ bản: **mọi thứ phía sau đều phụ thuộc vào dữ liệu**. Nếu dữ liệu sai thì chỉ báo kỹ thuật sai, model dự báo sai, backtest sai, AI Agent đưa ra lời khuyên sai. Không có nền tảng dữ liệu vững thì các module phía trên dù có xịn đến đâu cũng không đáng tin.

Cụ thể em đã hoàn thành:

| Hạng mục | Kết quả |
|----------|---------|
| **Thiết kế Medallion Architecture** | Bronze → Silver → Gold, có sơ đồ luồng dữ liệu rõ ràng |
| **Môi trường Docker** | 4 service: MySQL 8 (metadata), MinIO (object storage S3-compatible), Apache Iceberg REST Catalog, Apache Kafka 3.8 (KRaft mode) |
| **Module Bronze** | Lưu dữ liệu thô, kiểm tra schema, ghi lineage, xử lý trùng |
| **Module Silver** | Chuẩn hóa timestamp UTC, lọc OHLC không hợp lệ, ghi quality report |
| **Module Gold** | Tính MA, RSI, MACD, Bollinger Bands, target variable, volume profile |
| **Pipeline orchestrator** | Điều phối Bronze → Silver → Gold, ghi log, tính quality score |
| **Data source factory** | Kết nối yfinance, Finnhub, Alpha Vantage, web scraper, SSI iBoard |
| **MultiSource failover** | Tự động chuyển provider khi một nguồn lỗi |
| **Iceberg manager** | Time travel, schema evolution, ACID commit, snapshot management |

---

## 2. Kiến trúc tổng thể hệ thống

### 2.1. Sơ đồ luồng dữ liệu

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ yfinance │  │ Finnhub  │  │ Alpha    │  │  Web     │  │  SSI     │      │
│  │  (US)    │  │  (Global)│  │ Vantage  │  │ Scraper  │  │ iBoard   │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │             │             │             │             │            │
│       └─────────────┴─────┬───────┴────┬────────┴─────┬───────┘            │
│                           ▼            ▼             ▼                      │
│         ┌───────────────────────────────────────────────┐                  │
│         │           DataSourceFactory                   │                  │
│         │  (chọn provider theo biến môi trường DATA_SOURCE)│                │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌───────────────────────────────────────────────┐                  │
│         │              Ingestion Layer                   │                  │
│         │   Validate schema → Thêm ingestion_time, source │                 │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌───────────────────────────────────────────────┐                  │
│         │                 BRONZE                        │                  │
│         │  • Dữ liệu thô, giữ nguyên schema nguồn       │                  │
│         │  • Append-only, có ingestion_time + source    │                  │
│         │  • Phân vùng: symbol / year / month          │                  │
│         │  • Mỗi lần ghi tạo _lineage.json             │                  │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌───────────────────────────────────────────────┐                  │
│         │                 SILVER                        │                  │
│         │  • Timestamp UTC chuẩn hóa                   │                  │
│         │  • Dedup (symbol + timestamp)                 │                  │
│         │  • Lọc: missing, invalid OHLC, volume < 0    │                  │
│         │  • Bản ghi lỗi ghi vào _errors/              │                  │
│         │  • Ghi _quality.json sau mỗi lần transform   │                  │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌───────────────────────────────────────────────┐                  │
│         │                  GOLD                         │                  │
│         │  • MA(5/10/20/50), EMA(12/26)                │                  │
│         │  • RSI(14), MACD(12,26,9)                    │                  │
│         │  • Bollinger Bands(20,2σ)                    │                  │
│         │  • return_1d, return_5d, direction_1d (target)│                  │
│         │  • Candlestick patterns, volume profile       │                  │
│         └─────────────────────┬─────────────────────────┘                  │
│                               ▼                                              │
│         ┌──────────┬──────────┬──────────┬──────────────┐                   │
│         ▼          ▼          ▼          ▼              ▼                   │
│    Technical   Forecasting  Back-    AI Agent      FastAPI /                │
│    Analysis    (LSTM/ARIMA) testing  (Tool-based)  React UI                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2. Tại sao em chọn Medallion Architecture (Bronze – Silver – Gold)?

Thầy có thể hỏi: "Có nhiều kiến trúc data lake khác (lambda, kappa, single-layer), sao lại chọn Medallion?"

Lý do nằm ở 3 điểm em đã trải nghiệm trong quá trình xây dựng:

**Điểm 1 – Phân tách rõ ràng trách nhiệm mỗi tầng:**
Khi em cần sửa logic làm sạch ở Silver (ví dụ: phát hiện thêm quy tắc lọc `high < low`), em **chỉ cần chạy lại pipeline Silver → Gold** mà **không cần crawl lại từ nguồn**. Dữ liệu gốc ở Bronze vẫn còn nguyên. Với kiến trúc single-layer, mỗi lần đổi logic em lại phải fetch lại từ API → tốn request, có thể bị rate limit.

**Điểm 2 – Mỗi tầng phục vụ một nhóm người dùng khác nhau:**
- Bronze: data engineer debug lỗi nguồn cấp.
- Silver: analyst truy vấn dữ liệu sạch, hoặc modeler muốn tự tính feature riêng.
- Gold: data scientist cần dataset ML-ready, không phải mất công tính lại từ đầu.

**Điểm 3 – Truy vết (lineage) dễ dàng:**
Mỗi bản ghi ở Silver/Gold đều giữ `ingestion_time`, `source` từ Bronze. Khi thầy hỏi "tại sao RSI ngày 15/3 bị NaN?", em có thể truy về Bronze xem dữ liệu ngày đó có bị thiếu từ nguồn hay bị lọc ở Silver.

### 2.3. Code walkthrough – File nào tạo ra luồng trên?

#### 2.3.1. Abstract contract cho mọi data provider

Mọi provider (yfinance / Finnhub / SSI / …) đều implement 1 abstract class. Đây là "hợp đồng" — nếu class nào implement đủ 3 method thì có thể swap vào pipeline mà không phải đổi code.

```startLine:1:30:backend/app/data_sources/base.py
"""Abstract market data provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd


class StockDataProvider(ABC):
    """Contract for historical and latest OHLCV retrieval."""

    source_name: str = "abstract"

    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return historical OHLCV for a symbol."""

    @abstractmethod
    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        """Return the most recent bar(s) for a symbol."""

    @abstractmethod
    def validate_symbol(self, symbol: str) -> bool:
        """Return True if the symbol is supported by this provider."""
```

**Giải thích syntax cho người mới:**
- `from abc import ABC, abstractmethod`: `ABC` (Abstract Base Class) là class "khuôn mẫu" — không cho phép tạo instance trực tiếp. `@abstractmethod` đánh dấu method con **bắt buộc phải override**, nếu không sẽ lỗi lúc khởi tạo.
- `-> pd.DataFrame`: chú thích kiểu trả về (type hint), giúp IDE gợi ý và bắt bug.
- `start: datetime | None = None`: `|` là cú pháp Python 3.10+ cho union — cho phép nhận `datetime` hoặc `None`. Mặc định `None`.

#### 2.3.2. Factory – chọn provider theo biến môi trường

```startLine:1:99:backend/app/data_sources/factory.py
"""Factory for the configured market data provider."""

from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger
from app.data_sources.alpha_vantage_provider import AlphaVantageProvider
from app.data_sources.base import StockDataProvider
from app.data_sources.finnhub_provider import FinnhubProvider
from app.data_sources.multi_source import MultiSourceProvider
from app.data_sources.ssi_vn_provider import SSIVNProvider
from app.data_sources.web_scraper_provider import StockScraperProvider
from app.data_sources.yfinance_python_provider import YFinancePythonProvider

logger = get_logger(__name__)


def get_data_provider(name: str | None = None) -> StockDataProvider:
    """Return the provider selected by ENV or explicit name."""

    selected = (name or settings.data_source or "yfinance").lower()

    if selected == "sample":
        raise DataSourceError(
            "DATA_SOURCE=sample is no longer supported ..."
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

    if selected == "alpha_vantage":
        if not settings.alpha_vantage_api_key:
            raise DataSourceError(
                "DATA_SOURCE=alpha_vantage requires ALPHA_VANTAGE_API_KEY in .env ..."
            )
        ...
```

**Cơ chế hoạt động:**
1. Đọc `settings.data_source` (từ `.env` – xem `backend/app/core/config.py:100`).
2. Dò `if/elif` để chọn class tương ứng.
3. Nếu không có key (Alpha Vantage, Finnhub) → raise `DataSourceError` NGAY (fail-fast, không để lỗi lúc đang fetch).

**Cú pháp quan trọng:**
- `settings.alpha_vantage_api_key`: `settings` là singleton từ `lru_cache` (xem `config.py:13` `from functools import lru_cache`) — đọc `.env` 1 lần, cache vĩnh viễn.
- `raise DataSourceError(...)`: custom exception kế thừa `StockLakehouseError` (xem `core/exceptions.py:1-79`). Class cha gắn sẵn `status_code=502` (Bad Gateway — lỗi phía nguồn upstream) để FastAPI tự trả HTTP 502 khi lỗi này bubble lên.

#### 2.3.3. Multi-source – failover chain

```startLine:1:144:backend/app/data_sources/multi_source.py
"""Multi-source adapter with automatic failover."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

import pandas as pd

from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


DEFAULT_CHAINS: dict[str, list[str]] = {
    "1d": ["yfinance", "finnhub", "yfinance_direct", "alpha_vantage"],
    "1h": ["yfinance", "yfinance_direct", "finnhub"],
    "15m": ["yfinance", "yfinance_direct", "finnhub"],
    "5m": ["yfinance", "yfinance_direct"],
    "1m": ["yfinance"],
}


class MultiSourceProvider:
    """Try a chain of providers until one yields non-empty data."""

    def __init__(self, sources: Sequence[str] | None = None) -> None:
        from app.data_sources.factory import get_data_provider

        self._sources = list(sources or DEFAULT_CHAINS["1d"])
        self._providers = {name: get_data_provider(name) for name in self._sources}

    def get_historical_data(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        errors: dict[str, str] = {}
        for name in self._sources:
            provider = self._providers[name]
            try:
                frame = provider.get_historical_data(
                    symbol=symbol, start=start, end=end, interval=interval
                )
            except DataSourceError as exc:
                errors[name] = str(exc)
                logger.warning("[%s] failed for %s: %s", name, symbol, exc)
                continue

            if frame is None or frame.empty:
                errors[name] = "empty frame"
                continue

            return frame

        raise DataSourceError(
            f"All providers failed for {symbol} ({interval}): {errors}"
        )
```

**Cơ chế:**
- Tạo dict `_providers` map `name → instance` ngay trong `__init__` (lazy nhưng chỉ tạo 1 lần).
- Vòng `for ... in self._sources`: thử từng provider theo thứ tự ưu tiên. Cái nào trả `frame` không rỗng → done.
- Cuối cùng nếu tất cả fail → raise kèm dict lỗi để debug.

**Syntax đáng chú ý:**
- `Sequence[str] | None`: `Sequence` từ `typing` — bất kỳ kiểu iterable nào (list, tuple). Dùng thay vì `list` để hàm linh hoạt hơn.
- `errors: dict[str, str] = {}`: type hint cho biến local. Python ≥3.9 cho phép viết `dict[str, str]` thay vì `Dict[str, str]` từ `typing`.
- `provider = self._providers[name]`: subscript `dict[key]` trong Python. Nếu key không tồn tại → `KeyError`. Ở đây an toàn vì key đã được insert từ `sources`.

#### 2.3.4. Partition path – sinh đường dẫn Hive-style

```startLine:1:34:backend/app/lakehouse/parquet_manager.py
"""Parquet partition helpers for the medallion layers."""

from __future__ import annotations

from datetime import datetime

import pandas as pd


def partition_relative_path(symbol: str, timestamp: datetime, filename: str = "part-001.parquet") -> str:
    """Build a Hive-style partition path: symbol=AAPL/year=2026/month=09/part-001.parquet."""
    year = int(timestamp.year)
    month = int(timestamp.month)
    return f"symbol={symbol.upper()}/year={year}/month={month:02d}/{filename}"


def add_partition_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add year/month partition columns from timestamp."""
    result = frame.copy()
    ts = pd.to_datetime(result["timestamp"], utc=True)
    result["year"] = ts.dt.year.astype(int)
    result["month"] = ts.dt.month.astype(int)
    return result


def split_by_partition(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Group rows by symbol/year/month partition path."""
    partitioned = add_partition_columns(frame)
    grouped: dict[str, pd.DataFrame] = {}
    for (symbol, year, month), group in partitioned.groupby(["symbol", "year", "month"], sort=True):
        path = f"symbol={symbol}/year={int(year)}/month={int(month):02d}/part-001.parquet"
        grouped[path] = group.reset_index(drop=True)
    return grouped
```

**Cơ chế:**
- `synchronize_format` theo kiểu Hive: `symbol=AAPL/year=2026/month=09/part-001.parquet` — DuckDB, Spark, Athena đều đọc được.
- `f"...{month:02d}"`: format spec — `:02d` nghĩa là in **2 chữ số, padding số 0 phía trước** (VD: `9` → `"09"`, `12` → `"12"`).
- `groupby(["symbol","year","month"], sort=True)`: Gom nhóm theo nhiều cột. `sort=True` đảm bảo thứ tự ổn định.
- Kết quả `grouped`: `dict[path → DataFrame]`. Mỗi entry là 1 partition vật lý trên ổ đĩa / MinIO.

#### 2.3.5. Re-export qua `__init__.py`

```startLine:1:36:backend/app/lakehouse/__init__.py
"""Lakehouse storage and medallion layers."""

from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.fundamentals_silver import FundamentalsSilverLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.gold_features import GoldFeaturesLayer, GoldSentimentFeatures
from app.lakehouse.local_storage import LocalStorageBackend
from app.lakehouse.minio_storage import MinioStorageBackend
from app.lakehouse.news_silver import NewsSilverLayer
from app.lakehouse.pipeline import LakehousePipeline, PipelineConfig, PipelineRun, run_pipeline
from app.lakehouse.silver import SilverLayer
from app.lakehouse.storage_base import StorageBackend
from app.lakehouse.storage_factory import get_storage_backend

__all__ = [
    "StorageBackend", "LocalStorageBackend", "MinioStorageBackend", "get_storage_backend",
    "BronzeLayer", "SilverLayer", "GoldLayer",
    "NewsSilverLayer", "FundamentalsSilverLayer", "GoldFeaturesLayer", "GoldSentimentFeatures",
    "LakehousePipeline", "PipelineConfig", "PipelineRun", "run_pipeline",
]
```

**Lợi ích:**
- Từ ngoài chỉ cần `from app.lakehouse import BronzeLayer` thay vì `from app.lakehouse.bronze import BronzeLayer`.
- `__all__`: khai báo "public API" của package. Khi người khác `from app.lakehouse import *` chỉ nhận được những tên trong `__all__`.

#### 2.3.6. Docker compose – 4 service nền tảng

```startLine:1:84:docker-compose.yml
services:
  # ── Database ──────────────────────────────────────────────────────
  mysql:
    image: mysql:8.4
    container_name: stock-lakehouse-mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: "123456"
      MYSQL_DATABASE: stock_lakehouse
    ports:
      - "3307:3306"            # host 3307 → container 3306
    volumes:
      - mysql_data:/var/lib/mysql    # volume named → persist khi restart

  # ── Object Storage (S3-compatible) ────────────────────────────────
  minio:
    image: quay.io/minio/minio:latest
    container_name: stock-lakehouse-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"            # API
      - "9001:9001"            # Web console
    volumes:
      - minio_data:/data

  # ── Apache Iceberg REST Catalog ────────────────────────────────────
  iceberg-rest:
    image: tabulario/iceberg-rest:0.9.0
    container_name: stock-lakehouse-iceberg-rest
    environment:
      CATALOG_sqlite__catalog__uri: "sqlite:///var/lib/iceberg/iceberg_rest.db"
      CATALOG_s3__endpoint: "http://minio:9000"
      CATALOG_s3__access-key__id: "minioadmin"
      CATALOG_s3__secret-access-key: "minioadmin"
    ports:
      - "8181:8181"
    depends_on:
      - minio                     # chờ MinIO sẵn sàng trước khi start

  # ── Apache Kafka (KRaft – không cần ZooKeeper) ────────────────────
  kafka:
    image: apache/kafka:3.8.0
    environment:
      KAFKA_PROCESS_ROLES: controller,broker      # KRaft mode
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093,EXTERNAL://:9094
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,EXTERNAL://localhost:9094
    ports:
      - "9092:9092"            # internal (Docker network)
      - "9094:9094"            # external (host)
```

**Syntax đáng chú ý:**
- `image: mysql:8.4`: chỉ định Docker image + tag. `latest` = bản mới nhất.
- `restart: unless-stopped`: container tự restart khi Docker daemon khởi động lại, trừ khi user chủ động `stop`.
- `depends_on: - minio`: đảm bảo thứ tự start — Iceberg chỉ chạy sau khi MinIO đã start.
- `volumes: - mysql_data:/var/lib/mysql`: volume **named** (do Top 3 định nghĩa ở cuối file). Khi `docker compose down` (không có `-v`) thì data vẫn còn. Có `-v` mới xóa.
- `CATALOG_s3__endpoint`: convention env var của Iceberg REST — dấu `__` đại diện cho `.` (Iceberg parser tự map).

---

## 3. Tầng Bronze – Nơi dữ liệu gốc được giữ nguyên

### 3.1. Bronze là gì và tại sao cần nó?

Bronze là **vùng đệm** giữa nguồn cấp và tầng xử lý. Em giữ dữ liệu thô ở đây vì:

- **Không mất dữ liệu gốc**: Khi logic làm sạch ở Silver thay đổi, Bronze vẫn giữ nguyên bản gốc để em đối soát.
- **Debug dễ**: Nếu analyst phát hiện RSI sai, em có thể quay lại Bronze xem dữ liệu close ngày đó là bao nhiêu.
- **Audit trail**: Mỗi lần ghi đều kèm `_lineage.json` ghi rõ: ingest lúc nào, từ nguồn nào, bao nhiêu record, có trùng không.

### 3.2. Schema của Bronze

```python
BRONZE_SCHEMA = {
    "symbol":       "string",           # Mã chứng khoán, uppercase (VD: "VCB")
    "timestamp":    "datetime[ns, UTC]", # Thời điểm OHLCV bar (UTC, không timezone)
    "open":         "float64",          # Giá mở cửa
    "high":         "float64",          # Giá cao nhất
    "low":          "float64",          # Giá thấp nhất
    "close":        "float64",          # Giá đóng cửa
    "adj_close":    "float64",          # Giá điều chỉnh (split/dividend-adjusted)
    "volume":       "float64",          # Khối lượng giao dịch
    "source":       "string",           # Tên provider: "yfinance", "ssi_vn", "finnhub"
    "ingestion_time": "datetime[ns, UTC]", # Thời điểm em ghi vào Bronze
}
```

Tại sao lại có `adj_close`? Vì giá chứng khoán bị điều chỉnh khi có split hoặc cổ tức. Nếu em dùng giá chưa điều chỉnh thì khi tính return sẽ bị "bước nhảy" giả tạo. Nguồn yfinance có sẵn `Adj Close`, em giữ lại trong schema để sau này so sánh.

### 3.3. Cơ chế xử lý trùng lặp (deduplication)

Khi em chạy ingestion lần 2 cho cùng một mã, dữ liệu mới được nối với partition đã có:

```
Bronze/symbol=VCB/year=2024/month=01/
├── data_001.parquet  (100 records, ingest 2024-01-05)
└── data_002.parquet  (50 records, ingest 2024-01-10)
```

Code đọc tất cả file trong partition → `pd.concat` → `drop_duplicates(subset=["symbol","timestamp"], keep="last")` → ghi lại một file duy nhất. Tham số `keep="last"` nghĩa là **bản ghi mới hơn (ingestion mới hơn) được giữ**. Số bản ghi trùng được **đếm và ghi vào `_lineage.json`**, không âm thầm bỏ đi:

```json
{
  "layer": "bronze",
  "records_received": 50,
  "records_written": 45,
  "duplicate_count": 5,
  "partitions": ["symbol=VCB/year=2024/month=01"],
  "lineage": {
    "source": "ssi_vn",
    "symbol": "VCB",
    "type": "ohlcv",
    "interval": "1d"
  },
  "ingestion_time": "2024-01-10T08:00:00+00:00"
}
```

### 3.4. Tại sao phân vùng theo `symbol / year / month`?

Em chọn partition scheme này vì:

- **Symbol**: vì phần lớn query là "lấy hết dữ liệu của mã VCB" → DuckDB/Pandas filter theo `symbol=` là nhanh nhất, không cần quét toàn bộ data lake.
- **Year / month**: vì dữ liệu chứng khoán tích lũy theo thời gian. Một mã 10 năm lịch sử có thể có hàng chục nghìn rows. Tách theo tháng giúp query theo khoảng thời gian (VD: "lấy 6 tháng gần nhất") chỉ đọc đúng partition, không quét thừa.

### 3.5. Lineage tracking – Vì sao cần và hoạt động thế nào?

Lineage là **"giấy gốc"** của mỗi bản ghi. Khi thầy hỏi "dữ liệu VCB ngày 15/3 lấy từ đâu, lúc nào?", em mở `_lineage.json` trong partition của ngày đó là có đầy đủ. Cơ chế:

Mỗi khi `bronze.append()` được gọi → đọc metadata mới nhất của symbol đó → cộng thêm thông tin lần ingest hiện tại → ghi đè `_lineage.json`. File này ghi tất cả các lần ingest, có timestamp và source provider. Nếu sau này phát hiện dữ liệu ngày nào đó có vấn đề → tra lineage → biết lấy từ nguồn nào → request lại nếu cần.

### 3.6. Toàn bộ code `BronzeLayer` – từng dòng một

File `backend/app/lakehouse/bronze.py` (114 dòng):

```startLine:1:33:backend/app/lakehouse/bronze.py
"""Bronze layer: raw ingested OHLCV close to the source schema."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataValidationError, StorageError
from app.core.logging_config import get_logger
from app.lakehouse.parquet_manager import split_by_partition
from app.lakehouse.storage_base import StorageBackend
from app.lakehouse.storage_factory import get_storage_backend

logger = get_logger(__name__)

BRONZE_SCHEMA = {
    "symbol": "string",
    "timestamp": "datetime64[ns, UTC]",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "adj_close": "float64",
    "volume": "float64",
    "source": "string",
    "ingestion_time": "datetime64[ns, UTC]",
}


class BronzeLayer:
    """Append-only raw lakehouse zone with partition, lineage, and duplicate checks."""

    layer_name = "bronze"

    def __init__(self, storage: StorageBackend | None = None) -> None:
        self.storage = storage or get_storage_backend()
```

**Từ khoá `from __future__ import annotations`:**
- Kể từ Python 3.10, cho phép dùng cú pháp type hint mới (`dict[str, str]`, `list[int] | None`) mà không cần `from typing import ...`. Áp dụng cho toàn bộ file.

---

#### 3.6.1. `validate_schema` – ép kiểu cột

```startLine:42:56:backend/app/lakehouse/bronze.py
    def validate_schema(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Ensure required columns exist and types are coercible."""
        missing = [col for col in OHLCV_COLUMNS if col not in frame.columns]
        if missing:
            raise DataValidationError(f"Bronze schema missing columns: {missing}")
        result = frame[OHLCV_COLUMNS].copy()
        result["symbol"] = result["symbol"].astype(str).str.upper()
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
        result["ingestion_time"] = pd.to_datetime(result["ingestion_time"], utc=True)
        for col in ["open", "high", "low", "close", "adj_close", "volume"]:
            result[col] = pd.to_numeric(result[col], errors="coerce")
        result["source"] = result["source"].astype(str)
        return result
```

**Từng dòng:**
- `[col for col in OHLCV_COLUMNS if col not in frame.columns]`: **list comprehension** — duyệt qua 10 tên cột bắt buộc, lấy những cột **không có** trong DataFrame. `OHLCV_COLUMNS` định nghĩa ở `app/core/constants.py:108`.
- `result = frame[OHLCV_COLUMNS].copy()`: chọn đúng 10 cột + `.copy()` để không phải **SettingWithCopyWarning**.
- `.astype(str).str.upper()`: ép kiểu string rồi viết hoa (VCB chứ không phải vcb / Vcb).
- `pd.to_datetime(..., utc=True)`: chuyển string/timestamp thành `datetime64[ns, UTC]` — quan trọng để partition theo `year/month` chính xác.
- `pd.to_numeric(..., errors="coerce")`: nếu có giá trị lỗi (chuỗi không phải số) → thay bằng `NaN` thay vì raise.

#### 3.6.2. `append` – ghi Parquet có dedupe

```startLine:58:114:backend/app/lakehouse/bronze.py
    def append(self, frame: pd.DataFrame, lineage: dict | None = None) -> dict:
        """Append rows to partitioned Parquet files. Duplicates are counted, not silently ignored."""
        if frame.empty:
            raise DataValidationError("Cannot write empty frame to Bronze.")
        clean = self.validate_schema(frame)
        clean["ingestion_time"] = clean["ingestion_time"].fillna(pd.Timestamp.now(tz="UTC"))
        duplicate_count = int(clean.duplicated(subset=["symbol", "timestamp"]).sum())
        partitions = split_by_partition(clean)
        written_paths: list[str] = []
        records_written = 0
        for relative_path, group in partitions.items():
            existing = pd.DataFrame()
            if self.storage.exists(self.layer_name, relative_path):
                existing = self.storage.read_parquet(self.layer_name, relative_path)
            combined = pd.concat([existing, group], ignore_index=True)
            before = len(combined)
            combined = combined.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
            dropped = before - len(combined)
            duplicate_count += int(dropped)
            path = self.storage.write_parquet(self.layer_name, relative_path, combined)
            written_paths.append(path)
            records_written += len(group)
        metadata = {
            "layer": self.layer_name,
            "records_received": int(len(clean)),
            "records_written": records_written,
            "duplicate_count": duplicate_count,
            "partitions": list(partitions.keys()),
            "paths": written_paths,
            "lineage": lineage or {},
            "ingestion_time": datetime.now(timezone.utc).isoformat(),
            "storage_backend": self.storage.backend_name,
        }
        symbols = sorted(clean["symbol"].unique().tolist())
        for symbol in symbols:
            self.storage.write_json(
                self.layer_name,
                f"symbol={symbol}/_lineage.json",
                metadata,
            )
        logger.info(
            "Bronze append complete: received=%s duplicates=%s paths=%s",
            len(clean),
            duplicate_count,
            len(written_paths),
        )
        return metadata
```

**Cơ chế từng bước (rất quan trọng — đây là "trái tim" của Bronze):**

1. `split_by_partition(clean)` → dict `{path → DataFrame}`. Mỗi entry là 1 partition `symbol=AAPL/year=2026/month=09/part-001.parquet`.
2. Với mỗi partition: **đọc file cũ** (`existing`) nếu có, **concat** với batch mới.
3. `drop_duplicates(subset=["symbol","timestamp"], keep="last")` — giữ bản ghi **mới nhất** theo `ingestion_time` (vì đã concat nên row mới nằm dưới).
4. Đếm `dropped` (số dòng trùng bị bỏ) → cộng vào `duplicate_count`.
5. **Quan trọng**: ghi đè lại toàn bộ file Parquet (không append từng row). Đây là lý do Bronze "an toàn" với ACID — file Parquet là immutable, ta luôn ghi file mới rồi thay thế.
6. Cuối cùng với mỗi symbol → ghi `symbol=AAPL/_lineage.json` (metadata đầy đủ: records_received, duplicates, paths, lineage, timestamp).

**Syntax đáng học:**
- `int(...)` ép kiểu `numpy.int64` → Python `int` (để `json.dumps` serialize được).
- `lineage or {}`: toán tử `or` trả về `{}` nếu `lineage` là `None` / falsy.
- `f"symbol={symbol}/_lineage.json"`: f-string — nhúng biến vào string bằng `{...}`.
- `datetime.now(timezone.utc).isoformat()`: trả ISO 8601 string, ví dụ `"2026-10-02T08:15:00+00:00"`. Lưu ý: gọi `datetime.now(UTC)` thay vì `datetime.utcnow()` (deprecated từ Python 3.12).

#### 3.6.3. `read` – đọc tất cả partition của 1 mã

```startLine:104:114:backend/app/lakehouse/bronze.py
    def read(self, symbol: str) -> pd.DataFrame:
        """Read all Bronze partitions for a symbol."""
        frame = self.storage.read_prefix(self.layer_name, f"symbol={symbol.upper()}")
        if frame.empty:
            return frame
        return self.validate_schema(frame).sort_values("timestamp").reset_index(drop=True)

    def record_count(self, symbol: str | None = None) -> int:
        prefix = f"symbol={symbol.upper()}" if symbol else ""
        frame = self.storage.read_prefix(self.layer_name, prefix)
        return int(len(frame))
```

- `read_prefix(layer, prefix)`: tùy backend mà đọc khác nhau:
  - Local: `Path(root/bronze/symbol=VCB/).rglob("*.parquet")` → concat tất cả file Parquet.
  - MinIO: `client.list_objects(bucket, prefix="symbol=VCB/", recursive=True)` → tải từng object → concat.

---

## 4. Tầng Silver – Làm sạch có kiểm soát

### 4.1. Silver làm gì và tại sao không làm sạch ngay ở Bronze?

Câu hỏi tự nhiên: "Tại sao không validate dữ liệu ngay lúc ingest, cần gì thêm tầng Silver?"

Vì Bronze giữ nguyên dữ liệu gốc theo nguyên tắc **append-only**. Nếu em validate và sửa ở Bronze, em sẽ mất bản gốc. Silver là tầng **transformational** — nó tạo ra phiên bản sạch từ Bronze nhưng không xóa Bronze. Khi logic làm sạch thay đổi, em chạy lại Silver → Gold mà Bronze vẫn y nguyên.

### 4.2. Các quy tắc validation ở Silver

Em kiểm tra 4 loại lỗi:

| Loại lỗi | Quy tắc | Ví dụ |
|----------|---------|-------|
| **Missing** | Bất kỳ cột OHLCV hoặc timestamp nào NaN | `{open: NaN, high: 105, low: 100, close: 103}` |
| **Invalid OHLC** | `high < low`, `high < open`, `low > close`, `high < close` | `{open: 103, high: 100, low: 105, close: 102}` (high<low) |
| **Invalid volume** | `volume < 0` | `{volume: -5000}` |
| **Duplicate** | Trùng `(symbol, timestamp)` | Cùng mã, cùng ngày xuất hiện 2 lần |

### 4.3. Cơ chế ghi lại bản ghi lỗi – Điểm quan trọng nhất của Silver

Em **không xóa** bản ghi lỗi. Thay vào đó, bản ghi vi phạm được ghi vào:

```
Silver/_errors/errors_20240110T080000.parquet
```

File này có đầy đủ các cột OHLCV gốc + thêm cột `error_reason` để em biết bản ghi đó bị loại vì lý do gì:

```python
error_frame.loc[missing_mask,  "error_reason"] += "missing;"
error_frame.loc[invalid_ohlc,   "error_reason"] += "invalid_ohlc;"
error_frame.loc[invalid_volume, "error_reason"] += "invalid_volume;"
error_frame.loc[duplicate_mask, "error_reason"] += "duplicate;"
```

**Vì sao em không xóa luôn?** Vì:

- Nếu lỗi đến từ **bug ở nguồn cấp** (VD: SSI gửi sai timestamp), em cần thông báo cho bên cung cấp dữ liệu.
- Nếu lỗi đến từ **bug ở logic Silver** (VD: em đặt điều kiện sai), em có thể review lại và xử lý đúng mà không cần chạy lại từ nguồn.
- Nếu sau này nguồn cấp sửa lỗi, em có thể merge bản ghi lỗi vào dataset mà không mất dữ liệu.

### 4.4. Quality report – Bằng chứng chất lượng dữ liệu

Sau mỗi lần transform, em ghi `_quality.json` để thầy thấy rõ:

```json
{
  "engine": "pandas",
  "source_count": 12000,
  "record_count": 11950,
  "duplicate_count": 12,
  "missing_count": 15,
  "invalid_ohlc_count": 18,
  "invalid_volume_count": 5,
  "error_count": 50,
  "min_timestamp": "2020-01-02T00:00:00+00:00",
  "max_timestamp": "2024-01-10T00:00:00+00:00",
  "quality_status": "passed"
}
```

`quality_status` có 3 giá trị:
- `passed`: có dữ liệu hợp lệ và không có lỗi OHLC.
- `warning`: có dữ liệu nhưng có lỗi (bản ghi lỗi được ghi riêng, phần còn lại vẫn dùng được).
- `failed`: toàn bộ bị lỗi, không có record nào hợp lệ.

### 4.5. Pandas engine – Tại sao em không dùng Spark?

Em cân nhắc giữa Pandas (in-process) và Spark (distributed) cho Silver transform. Cuối cùng em chọn **Pandas làm engine chính** vì:

- **Dữ liệu hiện tại chưa đến ngưỡng cần Spark.** Mỗi symbol lịch sử 10 năm daily chỉ ~2.500 rows, cả Gold 50 symbols ~120.000 rows. Pandas xử lý thoải mái trong RAM laptop dev.
- **Spark tốn operational overhead**: cần Docker container riêng, JVM, khởi động cluster 15-30s, debug khó hơn.
- **Đồ án solo, ngân sách có hạn:** Một service Docker bớt đi = ít bề mặt lỗi khi demo trước hội đồng.
- **Schema nghiệp vụ giữ nguyên**: code Silver là Pandas, nhưng các bước validate (OHLC rule, dedupe, timezone) đều có thể chuyển sang Spark sau nếu scale lên vài triệu rows mà không phải đổi logic.

Vì vậy em bỏ luôn service Spark trong `docker-compose.yml`, giữ 4 service cốt lõi: MySQL, MinIO, Iceberg REST, Kafka.

### 4.6. Toàn bộ code `SilverLayer` – đọc thế nào

File `backend/app/lakehouse/silver.py` (171 dòng):

#### 4.6.1. Entry point – `transform` và `write`

```startLine:24:54:backend/app/lakehouse/silver.py
class SilverLayer:
    """Cleaned zone. Invalid records are reported, never silently dropped without counts."""

    layer_name = "silver"

    def __init__(self, storage: StorageBackend | None = None) -> None:
        self.storage = storage or get_storage_backend()

    def transform(self, bronze_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        """Clean Bronze data using Spark when enabled, otherwise Pandas."""
        if bronze_frame.empty:
            raise DataValidationError("Bronze frame is empty; cannot build Silver.")
        spark = get_spark_session() if spark_enabled() else None
        if spark is not None:
            return self._transform_spark(bronze_frame, spark)
        return self._transform_pandas(bronze_frame)

    def write(self, silver_frame: pd.DataFrame, quality_report: dict) -> dict:
        """Overwrite Silver partitions for the symbols present in the frame."""
        partitions = split_by_partition(silver_frame)
        paths = []
        for relative_path, group in partitions.items():
            paths.append(self.storage.write_parquet(self.layer_name, relative_path, group))
        for symbol in silver_frame["symbol"].unique():
            self.storage.write_json(
                self.layer_name,
                f"symbol={symbol}/_quality.json",
                quality_report,
            )
        return {"paths": paths, "records": int(len(silver_frame))}
```

- `tuple[pd.DataFrame, dict]` — return annotation cho biết `transform` trả về `(DataFrame, dict)`. Lưu ý Python ≥3.9 cần import `from __future__ import annotations` để dùng cú pháp này ở runtime.
- `spark_enabled()` từ `app/lakehouse/spark_session.py:14` — chỉ trả `True` khi `USE_SPARK=true` trong `.env`. Nếu `False` thì bỏ qua toàn bộ nhánh Spark.

#### 4.6.2. `_transform_pandas` – trái tim của Silver

```startLine:64:130:backend/app/lakehouse/silver.py
    def _transform_pandas(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        working = frame.copy()
        original_count = len(working)
        working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
        working["ingestion_time"] = pd.to_datetime(working["ingestion_time"], utc=True)
        for col in ["open", "high", "low", "close", "adj_close", "volume"]:
            working[col] = pd.to_numeric(working[col], errors="coerce")
        working["symbol"] = working["symbol"].astype(str).str.upper()

        missing_mask = working[["open", "high", "low", "close", "volume", "timestamp"]].isna().any(axis=1)
        duplicate_mask = working.duplicated(subset=["symbol", "timestamp"], keep="last")
        invalid_ohlc = ~(
            (working["high"] >= working["open"])
            & (working["high"] >= working["close"])
            & (working["low"] <= working["open"])
            & (working["low"] <= working["close"])
            & (working["high"] >= working["low"])
        )
        invalid_volume = working["volume"] < 0
        invalid_mask = missing_mask | invalid_ohlc | invalid_volume

        error_frame = working[invalid_mask | duplicate_mask].copy()
        error_frame["error_reason"] = ""
        error_frame.loc[missing_mask, "error_reason"] = error_frame.loc[missing_mask, "error_reason"] + "missing;"
        error_frame.loc[invalid_ohlc, "error_reason"] = error_frame.loc[invalid_ohlc, "error_reason"] + "invalid_ohlc;"
        error_frame.loc[invalid_volume, "error_reason"] = (
            error_frame.loc[invalid_volume, "error_reason"] + "invalid_volume;"
        )
        error_frame.loc[duplicate_mask, "error_reason"] = (
            error_frame.loc[duplicate_mask, "error_reason"] + "duplicate;"
        )

        valid = working[~invalid_mask].drop_duplicates(subset=["symbol", "timestamp"], keep="last")
        valid = valid.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

        if not error_frame.empty:
            self.storage.write_parquet(
                self.layer_name,
                f"_errors/errors_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.parquet",
                error_frame,
            )
            logger.warning("Silver rejected %s invalid/duplicate rows", len(error_frame))

        quality = {
            "engine": "pandas",
            "record_count": int(len(valid)),
            "source_count": int(original_count),
            "duplicate_count": int(duplicate_mask.sum()),
            "missing_count": int(missing_mask.sum()),
            "invalid_ohlc_count": int(invalid_ohlc.sum()),
            "invalid_volume_count": int(invalid_volume.sum()),
            "error_count": int(len(error_frame)),
            "min_timestamp": valid["timestamp"].min().isoformat() if not valid.empty else None,
            "max_timestamp": valid["timestamp"].max().isoformat() if not valid.empty else None,
            "quality_status": "passed" if not valid.empty and invalid_ohlc.sum() == 0 else "warning",
        }
        if valid.empty:
            quality["quality_status"] = "failed"
        return valid, quality
```

**Từng khối:**

**Khối 1 – ép kiểu:**
- `working.copy()`: bắt buộc `.copy()` để tránh **SettingWithCopyWarning** và không mutate DataFrame gốc.
- `pd.to_numeric(..., errors="coerce")`: string không parse được → `NaN`.

**Khối 2 – tạo mask lỗi:**
- `.isna().any(axis=1)`: trả Series boolean, `True` ở dòng có bất kỳ cột nào NaN.
- `working.duplicated(subset=["symbol","timestamp"], keep="last")`: đánh dấu dòng trùng (giữ `last` → đánh dấu những dòng **cũ** là trùng, dòng cuối là bản gốc).
- `invalid_ohlc`: là **phủ định** của 5 điều kiện "OHLC hợp lệ":
  - `high >= open` (cao nhất phải ≥ giá mở)
  - `high >= close` (cao nhất phải ≥ giá đóng)
  - `low <= open` (thấp nhất phải ≤ giá mở)
  - `low <= close` (thấp nhất phải ≤ giá đóng)
  - `high >= low` (cao ≥ thấp — nếu `high < low` là vô lý)
- `invalid_volume = working["volume"] < 0`: volume âm là sai.
- `invalid_mask = missing_mask | invalid_ohlc | invalid_volume`: dùng `|` (OR) giữa 3 Series boolean.

**Khối 3 – tạo error_frame:**
- `working[invalid_mask | duplicate_mask]`: lọc dòng lỗi **+** dòng trùng (không loại trùng vì ta vẫn muốn lưu lại để debug).
- `error_frame["error_reason"] = ""`: tạo cột mới, mặc định rỗng.
- `error_frame.loc[mask, "error_reason"] += "missing;"`: dùng `.loc[mask, col]` để gán theo điều kiện. **Lưu ý**: vì `error_reason` ban đầu là `""`, `+=` sẽ thành `"missing;"`. Nếu 1 dòng vừa missing vừa invalid OHLC, ta sẽ có `"missing;invalid_ohlc;"`.

**Khối 4 – tách valid:**
- `working[~invalid_mask]`: `~` là NOT — giữ dòng KHÔNG có lỗi OHLC.
- `.drop_duplicates(subset=["symbol","timestamp"], keep="last")`: bỏ trùng lần cuối, giữ bản mới nhất.

**Khối 5 – ghi `_errors/`:**
- Path: `_errors/errors_20261002T081500.parquet` (theo giờ UTC).
- Dùng `strftime("%Y%m%dT%H%M%S")` để timestamp trong tên file, sort được.

**Khối 6 – quality report:**
- `quality_status` = `"passed"` nếu có data hợp lệ VÀ không có OHLC lỗi.
- `= "warning"` nếu có data nhưng có OHLC lỗi (vẫn dùng được phần còn lại).
- `= "failed"` nếu `valid.empty` (toàn bộ bị loại).

#### 4.6.3. `_transform_spark` – nhánh tùy chọn (hiện không bật)

```startLine:132:171:backend/app/lakehouse/silver.py
    def _transform_spark(self, frame: pd.DataFrame, spark) -> tuple[pd.DataFrame, dict]:
        """Spark implementation with the same output schema as Pandas."""
        from pyspark.sql import functions as F
        from pyspark.sql.types import DoubleType, StringType, TimestampType
        ...
```

Chỉ chạy khi `USE_SPARK=true`. Logic tương đương Pandas nhưng dùng Spark SQL:

- `F.col("open").isNull() | (F.col("high") < F.col("open")) | ...`: OR các điều kiện invalid trong Spark column expression.
- `valid_sdf = sdf.filter(~invalid).dropDuplicates(["symbol", "timestamp"])`: lọc + dedupe trong Spark DataFrame.
- `.toPandas()` cuối cùng: chuyển về Pandas để trả ra ngoài (vì pipeline tiếp theo dùng Pandas).

---

## 5. Tầng Gold – Feature engineering sẵn sàng cho ML/DL

### 5.1. Gold là gì và tại sao cần tầng riêng?

Gold là tầng **analytics-ready**. Dữ liệu ở đây đã có đầy đủ features để:

- Vẽ chart với MA, RSI, MACD, Bollinger Bands.
- Train model (LSTM, ARIMA, Linear Regression).
- Chạy backtest với các chỉ báo kỹ thuật làm tín hiệu.
- AI Agent query để trả lời câu hỏi của user.

Em **tách Gold ra khỏi Silver** vì feature engineering là bước **tốn computation nhất** (rolling window 50 ngày, MACD phức tạp). Nếu mỗi lần train model lại phải tính lại từ đầu → lãng phí. Dataset Gold được tính một lần, dùng nhiều lần.

### 5.2. Các nhóm feature em tính

**Nhóm 1 – Price features (lợi nhuận):**
```python
return_1d  = (close_t - close_{t-1}) / close_{t-1}
return_5d  = (close_t - close_{t-5}) / close_{t-5}
log_return = ln(close_t / close_{t-1})
```
Công thức đơn giản nhưng quan trọng: `return_1d` chính là **target variable** khi em train model classification (hướng lên/xuống).

**Nhóm 2 – Moving averages:**
```python
sma_5  = rolling(window=5).mean(close)
sma_10 = rolling(window=10).mean(close)
sma_20 = rolling(window=20).mean(close)   # Phổ biến nhất trong trading
sma_50 = rolling(window=50).mean(close)
ema_12 = ewm(span=12).mean(close)        # EMA nhạy hơn SMA
ema_26 = ewm(span=26).mean(close)
```

**Nhóm 3 – RSI (Relative Strength Index):**
```python
delta      = close.diff()
gain       = delta.where(delta > 0, 0)
loss       = (-delta).where(delta < 0, 0)
avg_gain   = rolling(window=14).mean(gain)
avg_loss   = rolling(window=14).mean(loss)
rs         = avg_gain / avg_loss
rsi_14     = 100 - (100 / (1 + rs))
```
RSI > 70 → overbought (có thể giá sẽ giảm), RSI < 30 → oversold (có thể giá sẽ tăng). Đây là tín hiệu phổ biến trong các chiến lược trading.

**Nhóm 4 – MACD (Moving Average Convergence Divergence):**
```python
ema_12     = ewm(span=12).mean(close)
ema_26     = ewm(span=26).mean(close)
macd_line  = ema_12 - ema_26              # Đường MACD
signal     = ewm(span=9).mean(macd_line)   # Đường Signal
histogram  = macd_line - signal            # Histogram (dùng làm signal)
```
MACD cắt lên Signal → bullish, cắt xuống → bearish.

**Nhóm 5 – Bollinger Bands:**
```python
sma_20     = rolling(window=20).mean(close)
std_20     = rolling(window=20).std(close)
bb_upper   = sma_20 + 2 * std_20           # Dải trên
bb_middle  = sma_20                        # Dải giữa (SMA20)
bb_lower   = sma_20 - 2 * std_20           # Dải dưới
```
Giá chạm dải trên → overbought, chạm dải dưới → oversold.

**Nhóm 6 – Volume features:**
```python
volume_ratio = volume / rolling(window=20).mean(volume)
```
Volume > trung bình 20 ngày → có thể có sự kiện (tin tức, khối ngoại mua lớn).

**Nhóm 7 – Target variable (cho ML):**
```python
target_next_close = close_{t+1}     # Dùng shift(-1) — KHÔNG dùng close hiện tại
direction_1d     = 1 if close_{t+1} > close_t else 0  # Binary classification
```

### 5.3. Cơ chế tránh look-ahead leakage – Điểm cực kỳ quan trọng

Đây là câu hỏi thầy **chắc chắn sẽ hỏi**: "Làm sao đảm bảo model không nhìn thấy tương lai?"

**Nguyên tắc:** Tại thời điểm `t`, model chỉ được phép dùng thông tin từ `t` và quá khứ, **không được dùng** thông tin tại `t+1` trở đi.

**Cách em triển khai:**

```python
# ✅ ĐÚNG – shift(-1) lấy giá TRƯỚC đó
df["return_1d"] = df["close"].pct_change()  # (close_t - close_{t-1}) / close_{t-1}
df["sma_20"]    = df["close"].rolling(20).mean()  # Trung bình 20 ngày QUÁ KHỨ

# ❌ SAI – đây là leakage
df["future_return"] = df["close"].shift(-1)   # GÂY LEAKAGE!
```

Tất cả các indicator em dùng đều là **lagging indicators** (SMA, RSI, MACD, Bollinger) — chúng chỉ tính từ dữ liệu quá khứ. Em **không fill NaN bằng 0** ở đầu time series (vì 0 là giá trị có ý nghĩa trong trading) mà để nguyên — model sẽ tự skip các dòng có NaN.

**Chia train/test theo thời gian:**
```python
train = df[df["timestamp"] < "2023-01-01"]   # Train: trước 2023
test  = df[df["timestamp"] >= "2023-01-01"]  # Test: từ 2023 trở đi
```
Em **không dùng** `train_test_split` ngẫu nhiên của sklearn vì nó sẽ shuffle dữ liệu → model nhìn thấy tương lai trong tập train → **leakage nghiêm trọng**.

### 5.4. Idempotency – Tính chất quan trọng của Gold

Em thiết kế `build_gold_features()` sao cho **chạy bao nhiêu lần cũng cho kết quả giống nhau**:

```python
# Strip pre-existing derived columns trước khi tính lại
keep = [c for c in _BASE_INPUT_COLUMNS if c in frame.columns]
working_input = frame.loc[:, keep].copy()
```

Điều này có nghĩa: nếu Silver có chứa feature cũ (do lỗi pipeline trước), Gold sẽ strip đi và tính lại từ đầu. Em không phải xóa thủ công data lake mỗi khi muốn rebuild.

### 5.5. Toàn bộ code Gold – pipeline feature engineering

#### 5.5.1. `GoldLayer` – class mỏng, ủy quyền cho `build_gold_features`

```startLine:1:65:backend/app/lakehouse/gold.py
"""Gold layer: analytics-ready features and targets without look-ahead leakage."""

from __future__ import annotations

import pandas as pd

from app.core.exceptions import DataValidationError
from app.core.logging_config import get_logger
from app.features.feature_engineering import build_gold_features
from app.lakehouse.parquet_manager import split_by_partition
from app.lakehouse.spark_session import get_spark_session, spark_enabled
from app.lakehouse.storage_base import StorageBackend
from app.lakehouse.storage_factory import get_storage_backend

logger = get_logger(__name__)


class GoldLayer:
    """Feature and target zone consumed by TA, ML, DL, backtesting, and dashboards."""

    layer_name = "gold"

    def __init__(self, storage: StorageBackend | None = None) -> None:
        self.storage = storage or get_storage_backend()

    def transform(self, silver_frame: pd.DataFrame) -> pd.DataFrame:
        """Build Gold features. Spark is used for column-level transforms when enabled."""
        if silver_frame.empty:
            raise DataValidationError("Silver frame is empty; cannot build Gold.")
        spark = get_spark_session() if spark_enabled() else None
        if spark is not None:
            return self._transform_spark(silver_frame, spark)
        return build_gold_features(silver_frame)

    def write(self, gold_frame: pd.DataFrame) -> dict:
        partitions = split_by_partition(gold_frame)
        paths = []
        for relative_path, group in partitions.items():
            paths.append(self.storage.write_parquet(self.layer_name, relative_path, group))
        logger.info("Gold write complete: %s rows, %s partitions", len(gold_frame), len(paths))
        return {"paths": paths, "records": int(len(gold_frame))}

    def read(self, symbol: str) -> pd.DataFrame:
        frame = self.storage.read_prefix(self.layer_name, f"symbol={symbol.upper()}")
        if frame.empty:
            return frame
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.loc[:, ~frame.columns.duplicated()]
        return frame.sort_values("timestamp").reset_index(drop=True)
```

**So với Bronze/Silver:**
- `transform` không trả về `(frame, quality_report)` vì ở Gold **không có khái niệm "lỗi"** — tất cả NaN do rolling window (50 dòng đầu) là hợp lệ.
- `~frame.columns.duplicated()`: phòng trường hợp `pd.concat` trước đó tạo cột trùng tên, ta giữ cột đầu tiên.

#### 5.5.2. `build_gold_features` – orchestrator tính tất cả feature

```startLine:1:103:backend/app/features/feature_engineering.py
"""Gold-layer feature engineering orchestrator."""

from __future__ import annotations

import pandas as pd

from app.core.exceptions import DataValidationError
from app.features.advanced_features import (
    add_advanced_indicators,
    add_candlestick_features,
    add_volume_profile_features,
    add_composite_signals,
)
from app.features.macro_features import MacroFeatureBuilder, add_market_regime_features
from app.features.price_features import add_price_features
from app.features.target_features import add_target_features
from app.features.technical_features import add_technical_features

# Columns that are *not* derived features - everything else is considered a
# prior derived feature and is dropped before we re-derive them.  This makes
# build_gold_features idempotent and tolerant of contaminated Silver inputs.
_BASE_INPUT_COLUMNS = (
    "symbol", "timestamp", "open", "high", "low", "close", "adj_close", "volume",
    "source", "ingestion_time", "year", "month",
)


def build_gold_features(frame: pd.DataFrame, include_macro: bool = True) -> pd.DataFrame:
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise DataValidationError(f"Feature engineering missing columns: {sorted(missing)}")

    # Strip any pre-existing derived columns so the pipeline is idempotent.
    keep = [c for c in _BASE_INPUT_COLUMNS if c in frame.columns]
    working_input = frame.loc[:, keep].copy()

    parts: list[pd.DataFrame] = []
    macro_builder = MacroFeatureBuilder() if include_macro else None

    for symbol, group in working_input.groupby("symbol", sort=True):
        ordered = group.sort_values("timestamp").copy().reset_index(drop=True)

        ordered = add_technical_features(ordered)
        ordered = add_price_features(ordered)
        ordered = add_target_features(ordered)
        ordered = add_advanced_indicators(ordered)
        ordered = add_candlestick_features(ordered)
        ordered = add_volume_profile_features(ordered)
        ordered = add_composite_signals(ordered)
        ordered = add_market_regime_features(ordered)

        if macro_builder is not None and len(ordered) > 50:
            try:
                ordered = macro_builder.build(ordered)
            except Exception:
                pass

        ordered["symbol"] = symbol
        parts.append(ordered)

    result = pd.concat(parts, ignore_index=True)
    return result.loc[:, ~result.columns.duplicated()]


def build_gold_features_simple(frame: pd.DataFrame) -> pd.DataFrame:
    return build_gold_features(frame, include_macro=False)


def drop_warmup_rows(frame: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    return frame.dropna(subset=feature_columns).reset_index(drop=True)
```

**Cơ chế:**
- `_BASE_INPUT_COLUMNS`: tuple 12 tên cột "gốc" — tất cả các cột khác đều là derived → strip đi trước khi tính lại. Đây là chìa khoá idempotent.
- `groupby("symbol", sort=True)`: xử lý từng mã **độc lập** để rolling window không bị "lẫn" giữa 2 mã khác nhau.
- Chuỗi `add_*`: mỗi hàm **trả về DataFrame mới** (không mutate input), gán lại vào `ordered`.
- `try/except Exception: pass` quanh macro builder: nếu API macro fail (offline), vẫn trả về Gold đầy đủ.

#### 5.5.3. `add_technical_features` – gọi 5 indicator

```startLine:1:11:backend/app/features/technical_features.py
"""Technical indicator features for the Gold layer."""

from __future__ import annotations

import pandas as pd

from app.indicators.service import IndicatorConfig, add_indicators


def add_technical_features(frame: pd.DataFrame, config: IndicatorConfig | None = None) -> pd.DataFrame:
    """Attach SMA/EMA/RSI/MACD/Bollinger features."""
    return add_indicators(frame, config=config)
```

→ Wrapper 1 dòng. Công việc thật ở `app/indicators/service.py`.

```startLine:25:73:backend/app/indicators/service.py
@dataclass
class IndicatorConfig:
    """User-configurable indicator parameters."""

    sma_windows: tuple[int, ...] = (5, 10, 20, 50)
    ema_windows: tuple[int, ...] = (12, 26)
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_window: int = 20
    bb_std: float = 2.0


RESERVED_COLUMNS = {
    "sma_5", "sma_10", "sma_20", "sma_50",
    "ema_12", "ema_26",
    "rsi_14",
    "macd", "macd_signal", "macd_hist",
    "bb_middle", "bb_upper", "bb_lower",
}


def add_indicators(frame: pd.DataFrame, config: IndicatorConfig | None = None) -> pd.DataFrame:
    """Attach SMA, EMA, RSI, MACD, and Bollinger columns to an OHLCV frame."""
    if "close" not in frame.columns:
        raise ValueError("Indicator calculation requires a close column.")
    config = config or IndicatorConfig()
    # Drop any pre-existing indicator columns so the function is idempotent.
    result = frame.drop(columns=[c for c in RESERVED_COLUMNS if c in frame.columns]).copy()
    close = result["close"]
    for window in config.sma_windows:
        result[f"sma_{window}"] = sma(close, window)
    for window in config.ema_windows:
        result[f"ema_{window}"] = ema(close, window)
    result["rsi_14"] = rsi(close, config.rsi_period)
    macd_frame = macd(close, config.macd_fast, config.macd_slow, config.macd_signal)
    result = pd.concat([result, macd_frame], axis=1)
    bands = bollinger_bands(close, config.bb_window, config.bb_std)
    result = pd.concat([result, bands], axis=1)
    return result
```

**Cú pháp quan trọng:**
- `@dataclass`: decorator của module `dataclasses` — tự sinh `__init__`, `__repr__`, `__eq__`. Cho phép `IndicatorConfig()` thay vì viết constructor.
- `tuple[int, ...] = (5, 10, 20, 50)`: tuple **bất biến**, default value của dataclass field.
- `RESERVED_COLUMNS = {...}`: `set` (tập hợp), lookup O(1).
- `frame.drop(columns=[c for c in RESERVED_COLUMNS if c in frame.columns]).copy()`: idempotency — nếu đã có `sma_20` thì drop trước khi tính lại.
- `pd.concat([result, macd_frame], axis=1)`: `axis=1` nghĩa là ghép **cột** (cùng index). `axis=0` sẽ ghép dòng.

#### 5.5.4. Từng indicator – pure Pandas

```startLine:1:11:backend/app/indicators/sma.py
def sma(series: pd.Series, window: int) -> pd.Series:
    """Return the simple moving average of `series` over `window` periods."""
    if window <= 0:
        raise ValueError("SMA window must be a positive integer.")
    return series.astype(float).rolling(window=window, min_periods=window).mean()
```

- `series.rolling(window=20).mean()`: Pandas rolling — cửa sổ trượt 20 dòng.
- `min_periods=window`: bắt buộc đủ 20 quan sát mới ra số. Nếu thiếu → `NaN`. Đây là lý do 49 dòng đầu của SMA_50 bị NaN.

```startLine:1:11:backend/app/indicators/ema.py
def ema(series: pd.Series, window: int) -> pd.Series:
    if window <= 0:
        raise ValueError("EMA window must be a positive integer.")
    return series.astype(float).ewm(span=window, adjust=False, min_periods=window).mean()
```

- `ewm(span=20, adjust=False)`: **Exponential** Weighted Moving Average — trọng số giảm theo cấp số nhân. `span=20` tương đương `alpha = 2/(20+1)`.
- `adjust=False`: dùng công thức recursive (Wilder smoothing), không quay lui về đầu chuỗi.

```startLine:1:23:backend/app/indicators/rsi.py
def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Return RSI values in [0, 100] for the given close series."""
    if period <= 0:
        raise ValueError("RSI period must be a positive integer.")
    close = series.astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    result = result.mask(avg_loss.eq(0) & avg_gain.gt(0), 100.0)
    result = result.mask(avg_gain.eq(0) & avg_loss.gt(0), 0.0)
    return result.astype(float)
```

- `delta.clip(lower=0)`: chỉ giữ phần dương (gain).
- `delta.clip(upper=0)`: chỉ giữ phần âm → đảo dấu thành loss dương.
- `ewm(alpha=1/period)`: Wilder smoothing — `alpha = 1/14`.
- `rs = avg_gain / avg_loss`: Relative Strength.
- `100 - 100/(1+rs)`: công thức RSI cổ điển.
- `result.mask(...)`: set giá trị đặc biệt khi `avg_loss=0` (RSI=100) hoặc `avg_gain=0` (RSI=0).

```startLine:1:25:backend/app/indicators/macd.py
def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    close = series.astype(float)
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist},
        index=series.index,
    )
```

- MACD = `EMA_12 - EMA_26`. Signal = `EMA_9(MACD)`. Histogram = `MACD - Signal`.

```startLine:1:23:backend/app/indicators/bollinger.py
def bollinger_bands(series: pd.Series, window: int = 20, std_multiplier: float = 2.0) -> pd.DataFrame:
    close = series.astype(float)
    middle = sma(close, window)
    rolling_std = close.rolling(window=window, min_periods=window).std()
    upper = middle + std_multiplier * rolling_std
    lower = middle - std_multiplier * rolling_std
    return pd.DataFrame(
        {"bb_middle": middle, "bb_upper": upper, "bb_lower": lower},
        index=series.index,
    )
```

- Bollinger: middle = SMA_20, upper = SMA + 2σ, lower = SMA - 2σ.

#### 5.5.5. `add_price_features` và `add_target_features` – chống leakage

```startLine:1:23:backend/app/features/price_features.py
def add_price_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    close = result["close"].astype(float)
    volume = result["volume"].astype(float)
    result["return"] = close.pct_change()
    result["log_return"] = np.log(close / close.shift(1))
    result["price_change"] = close.diff()
    result["volume_change"] = volume.pct_change()
    result["rolling_std_20"] = result["return"].rolling(window=20, min_periods=20).std()
    result["rolling_min_20"] = close.rolling(window=20, min_periods=20).min()
    result["rolling_max_20"] = close.rolling(window=20, min_periods=20).max()
    result["volume_ma_20"] = volume.rolling(window=20, min_periods=20).mean()
    result["close_lag_1"] = close.shift(1)
    result["close_lag_2"] = close.shift(2)
    result["return_lag_1"] = result["return"].shift(1)
    result["volume_lag_1"] = volume.shift(1)
    return result
```

- `close.pct_change()` = `(close_t - close_{t-1}) / close_{t-1}` — return 1 ngày.
- `np.log(close / close.shift(1))`: log-return = `ln(close_t) - ln(close_{t-1})`.
- `.shift(1)`: giá trị **1 dòng trước** (lag). Dùng làm feature cho model.
- `.rolling(20).std()`: độ biến động 20 ngày.

```startLine:1:21:backend/app/features/target_features.py
def add_target_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add next-bar close, return, and direction. The last row is NaN by design."""
    result = frame.copy()
    close = result["close"].astype(float)
    result["target_close_next"] = close.shift(-1)
    result["target_return_next"] = close.pct_change().shift(-1)
    result["target_direction_next"] = np.where(
        result["target_return_next"] > 0,
        1,
        np.where(result["target_return_next"].isna(), np.nan, 0),
    )
    return result
```

**Đây là phần quan trọng nhất về leakage:**
- `close.shift(-1)`: lấy giá **1 dòng sau** (future). Nếu thầy hỏi "model nhìn tương lai à?" → Đúng, đây là **target**, không phải feature.
- `target_direction_next`: 1 nếu `target_return_next > 0`, 0 nếu ≤ 0, NaN nếu target NaN.
- Dòng cuối cùng **luôn NaN** vì không có "ngày mai" → tự skip lúc train.

---

## 6. Pipeline điều phối luồng Bronze → Silver → Gold

### 6.1. Cơ chế hoạt động của Pipeline

Em viết `LakehousePipeline` trong `app/lakehouse/pipeline.py` để điều phối toàn bộ luồng. Khi gọi:

```python
pipeline = LakehousePipeline(config)
result = pipeline.run(symbols=["VCB", "FPT", "HPG"])
```

Pipeline thực hiện tuần tự 3 bước:

```
Bước 1: _ingest_bronze(symbols)
  └── provider.get_historical_data(symbol, start, end)
  └── bronze.append(frame, lineage={...})
  └── Ghi: bronze_records, duplicate_count

Bước 2: _transform_silver(symbols)
  └── bronze.read(symbol)
  └── silver.transform(bronze_frame)
  └── silver.write(silver_frame, quality_report)
  └── Ghi: silver_records, invalid_records

Bước 3: _transform_gold(symbols)
  └── silver.read(symbol)
  └── gold.transform(silver_frame)
  └── gold.write(gold_frame)
  └── Ghi: gold_records
```

Mỗi bước **độc lập**: nếu Silver thất bại → pipeline dừng, không chạy Gold. Error được ghi vào `PipelineRun.errors`, không âm thầm bỏ qua.

### 6.2. Quality score – Điểm chất lượng tổng thể

Sau khi chạy xong, pipeline tính `quality_score` (0–100%):

```
base_score = 100
- error_penalty     = số_errors × 10
- duplicate_rate    = duplicates / bronze_records × 20
- invalid_rate      = invalid_records / silver_records × 30
- retention_penalty = -20 nếu gold_records < bronze_records × 50%
```

Quality score giúp em nhanh chóng biết pipeline có vấn đề không mà không cần mở từng file JSON.

### 6.3. Pipeline metadata – `PipelineRun`

Mỗi lần chạy tạo ra một `PipelineRun` với đầy đủ thông tin:

```json
{
  "run_id": "a3f2b1c0",
  "started_at": "2024-01-10T08:00:00+00:00",
  "completed_at": "2024-01-10T08:01:30+00:00",
  "status": "success",
  "bronze_records": 12000,
  "silver_records": 11950,
  "gold_records": 11950,
  "duplicates_removed": 50,
  "invalid_records": 0,
  "quality_score": 97.3,
  "symbols_processed": ["VCB", "FPT", "HPG"],
  "storage_backend": "minio",
  "errors": [],
  "warnings": []
}
```

File này được lưu lại (em sẽ lưu vào MySQL hoặc log ở tuần 3) để track lịch sử chạy.

### 6.4. Toàn bộ code `LakehousePipeline` – orchestrator

File `backend/app/lakehouse/pipeline.py` (411 dòng). Đây là file quan trọng nhất vì nó **nối 3 layer + provider + storage + PipelineRun**.

#### 6.4.1. PipelineConfig + PipelineRun – dataclass

```startLine:55:120:backend/app/lakehouse/pipeline.py
@dataclass
class PipelineConfig:
    """Configuration for lakehouse pipeline."""

    use_minio: bool = False
    use_iceberg: bool = False
    use_spark: bool = False

    symbols: list[str] | None = None
    interval: str = "1d"
    lookback_days: int = 730

    skip_silver: bool = False
    skip_gold: bool = False

    data_source: str = "yfinance"


@dataclass
class PipelineRun:
    """Record of a pipeline execution."""

    run_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: str = "running"

    bronze_records: int = 0
    silver_records: int = 0
    gold_records: int = 0

    duplicates_removed: int = 0
    invalid_records: int = 0
    quality_score: float = 0.0

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    symbols_processed: list[str] = field(default_factory=list)
    storage_backend: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            ...
        }
```

**Cú pháp quan trọng:**
- `@dataclass`: tự generate `__init__`. Cú pháp `field bronze_records: int = 0` nghĩa là field không bắt buộc, mặc định 0.
- `field(default_factory=lambda: datetime.now(timezone.utc))`: dùng **lambda factory** thay vì default cứng, vì `datetime.now()` phải gọi lúc khởi tạo instance (không phải lúc import module).
- `field(default_factory=list)`: tương tự, dùng `list` (callable) để tạo list rỗng mới mỗi lần — nếu dùng `= []` sẽ share cùng 1 list giữa các instance (bug khét tiếng).

#### 6.4.2. Hàm `run` – entry point

```startLine:152:208:backend/app/lakehouse/pipeline.py
    def run(self, symbols: list[str] | None = None) -> PipelineRun:
        import uuid

        self.current_run = PipelineRun(
            run_id=str(uuid.uuid4())[:8],
            storage_backend=self.storage.backend_name,
        )

        symbols = symbols or self.config.symbols or []
        self.current_run.symbols_processed = symbols

        logger.info(f"Starting pipeline run {self.current_run.run_id}")
        ...

        try:
            self._ingest_bronze(symbols)
            if not self.config.skip_silver:
                self._transform_silver(symbols)
            if not self.config.skip_gold:
                self._transform_gold(symbols)

            self._calculate_quality_score()
            self.current_run.status = "success"
            self.current_run.completed_at = datetime.now(timezone.utc)
        except Exception as e:
            self.current_run.status = "failed"
            self.current_run.completed_at = datetime.now(timezone.utc)
            self.current_run.errors.append(str(e))

        return self.current_run
```

**Cơ chế:**
- `uuid.uuid4()` sinh UUID 128-bit ngẫu nhiên; `[:8]` cắt lấy 8 ký tự đầu làm `run_id` ngắn gọn.
- `try ... except Exception as e`: **nuốt mọi exception** nhưng ghi vào `errors` thay vì crash. Trả về `PipelineRun` với `status="failed"` — caller vẫn nhận được object đầy đủ thông tin.
- `_ingest_bronze` → `_transform_silver` → `_transform_gold`: tuần tự, nếu Bronze fail thì không chạy Silver.

#### 6.4.3. `_ingest_bronze`

```startLine:210:259:backend/app/lakehouse/pipeline.py
    def _ingest_bronze(self, symbols: list[str]) -> None:
        from app.data_sources import get_data_provider

        provider = get_data_provider(self.config.data_source)

        total_records = 0
        total_duplicates = 0

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.config.lookback_days)

        for symbol in symbols:
            try:
                frame = provider.get_historical_data(
                    symbol,
                    start=start,
                    end=end,
                    interval=self.config.interval,
                )

                if frame.empty:
                    self.current_run.warnings.append(f"No data for {symbol}")
                    continue

                metadata = self.bronze.append(frame, lineage={
                    "source": self.config.data_source,
                    "symbol": symbol,
                    "type": "ohlcv",
                    "interval": self.config.interval,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                })

                total_records += metadata["records_written"]
                total_duplicates += metadata["duplicate_count"]

            except Exception as e:
                self.current_run.errors.append(f"Bronze ingest failed for {symbol}: {e}")

        self.current_run.bronze_records = total_records
        self.current_run.duplicates_removed = total_duplicates
```

- **Local import** `from app.data_sources import get_data_provider` trong hàm (không ở đầu file) — pattern chống **circular import**. Module `data_sources/factory.py` import từ `core`, và ngược lại. Đặt local là cách chuẩn.
- `lineage={...}` dict ghi vào `_lineage.json` ngay sau khi ghi Parquet.
- Mỗi mã có try/except riêng — 1 mã lỗi không chặn các mã còn lại.

#### 6.4.4. `_calculate_quality_score`

```startLine:329:355:backend/app/lakehouse/pipeline.py
    def _calculate_quality_score(self) -> None:
        if self.current_run.bronze_records == 0:
            if self.current_run.silver_records > 0:
                self.current_run.quality_score = 95.0
            else:
                self.current_run.quality_score = 0.0
            return

        error_penalty = len(self.current_run.errors) * 10
        duplicate_rate = (
            self.current_run.duplicates_removed /
            max(1, self.current_run.bronze_records)
        )
        invalid_rate = (
            self.current_run.invalid_records /
            max(1, self.current_run.silver_records)
        )

        base_score = 100.0
        base_score -= error_penalty
        base_score -= duplicate_rate * 20
        base_score -= invalid_rate * 30

        if self.current_run.bronze_records > 0:
            retention = self.current_run.gold_records / self.current_run.bronze_records
            if retention < 0.5:
                base_score -= 20

        self.current_run.quality_score = max(0.0, min(100.0, base_score))
```

**Cú pháp cần nhớ:**
- `max(1, X)`: tránh chia cho 0 khi X=0. Đây là **guard chống ZeroDivisionError**.
- `max(0.0, min(100.0, base_score))`: clamp về [0, 100]. `min` trả giá trị nhỏ hơn, `max` trả lớn hơn.

#### 6.4.5. Endpoint FastAPI bọc pipeline

```startLine:88:115:backend/app/api/v1/endpoints/pipeline.py
@router.post("/run", response_model=PipelineRunResponse)
async def run_lakehouse_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
    symbols = request.symbols or SUPPORTED_SYMBOLS
    config = PipelineConfig(
        use_minio=request.use_minio,
        symbols=symbols,
        interval=request.interval,
        lookback_days=request.lookback_days,
        skip_silver=request.skip_silver,
        skip_gold=request.skip_gold,
    )
    pipeline = LakehousePipeline(config)
    result = pipeline.run(symbols)
    return PipelineRunResponse(**result.to_dict())
```

**Cú pháp:**
- `@router.post("/run", response_model=PipelineRunResponse)`: decorator của FastAPI. Bất kỳ ai POST `/api/v1/pipeline/run` với body JSON match `PipelineRunRequest` sẽ chạy hàm này.
- `request.symbols or SUPPORTED_SYMBOLS`: nếu client không gửi list symbols → mặc định chạy toàn bộ 60 mã US.
- `PipelineRunResponse(**result.to_dict())`: unpacking dict thành keyword args của constructor Pydantic.

---

### 6.5. Pipeline đơn giản cho 1 mã – dùng cho CLI

Ngoài `LakehousePipeline` đầy đủ, có 1 pipeline "gọn" cho 1 symbol, dùng trong CLI scripts. Toàn bộ logic nằm trong **1 file duy nhất** `orchestrator.py`:

```startLine:1:32:backend/app/pipelines/orchestrator.py
"""
Medallion pipeline orchestrator — single entry point for Bronze → Silver → Gold.
This module replaces 7 fragmented files (ingestion, transformation, validation, quality, feature_pipeline, pipeline_runner) into one clean orchestrator.
"""
from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd
from app.core.exceptions import DataValidationError
from app.core.logging_config import get_logger
from app.data_sources.factory import get_data_provider
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer
logger = get_logger(__name__)

# ── Stage 1: Ingest ──────────────────────────────────────────────
def ingest_symbol(symbol, interval="1d", ...): ...

# ── Stage 2: Validate ─────────────────────────────────────────────
def validate_ohlc_frame(frame: pd.DataFrame) -> dict[str, int]: ...

# ── Stage 3: Bronze → Silver ────────────────────────────────────
def transform_to_silver(symbol, ...) -> dict: ...

# ── Stage 4: Quality gate ─────────────────────────────────────────
def build_quality_report(symbol) -> dict: ...
def assert_quality_passed(report) -> None: ...

# ── Stage 5: Silver → Gold ──────────────────────────────────────
def build_gold_layer(symbol) -> dict: ...

# ── Stage 6: Full pipeline (idempotent) ─────────────────────────
def run_symbol_pipeline(symbol, interval="1d", ...,
                       ingest=True, skip_silver=False, skip_gold=False) -> dict:
    """Run the complete medallion pipeline for one symbol. All stages idempotent."""
    started = datetime.now(timezone.utc)
    if ingest: ingest_symbol(...)
    if not skip_silver: silver_meta = transform_to_silver(...)
    quality = build_quality_report(symbol)
    assert_quality_passed(quality)
    if not skip_gold: gold_meta = build_gold_layer(symbol)
    return {
        "pipeline_name": "stock_lakehouse_pipeline",
        "symbol": symbol.upper(),
        "status": "success",
        "start_time": started,
        "records_processed": gold_meta.get("records", 0),
        "quality": quality,
        "gold": gold_meta,
    }
```

**Tại sao có 2 pipeline?**
- `LakehousePipeline` (`app/lakehouse/pipeline.py`): chạy nhiều symbol, có quality score, có errors/warnings. Dùng cho **API**.
- `run_symbol_pipeline` (`app/pipelines/orchestrator.py`): chạy 1 symbol, raise ngay nếu lỗi. Dùng cho **CLI scripts** như `scripts/ingest_historical.py`.

**Các stage chính** (tất cả nằm trong `orchestrator.py`):

| Hàm | Stage | Chi tiết |
|------|-------|--------|
| `ingest_symbol` | Bronze | Fetch từ provider → `BronzeLayer.append()` |
| `transform_to_silver` | Bronze→Silver | `BronzeLayer.read()` → `SilverLayer.transform()` → `SilverLayer.write()` |
| `validate_ohlc_frame` | Quality gate | Đếm missing/duplicate/invalid_ohlc/volume |
| `build_quality_report` | Quality gate | Tổng hợp thành report JSON |
| `assert_quality_passed` | Quality gate | Raise nếu `quality_status == "failed"` |
| `build_gold_layer` | Silver→Gold | `SilverLayer.read()` → `GoldLayer.transform()` → `GoldLayer.write()` |

**`validate_ohlc_frame`** — logic core (trong `orchestrator.py`):

```startLine:111:162:backend/app/pipelines/orchestrator.py
def validate_ohlc_frame(frame: pd.DataFrame) -> dict[str, int]:
    """Count validation issues without mutating the input."""
    required = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
    missing_cols = [col for col in required if col not in frame.columns]
    if missing_cols:
        raise DataValidationError(f"Validation missing columns: {missing_cols}")
    missing_count = int(frame[required].isna().any(axis=1).sum())
    duplicate_count = int(frame.duplicated(subset=["symbol", "timestamp"]).sum())
    invalid_ohlc_count = int(
        (~(
            (frame["high"] >= frame["open"])
            & (frame["high"] >= frame["close"])
            & (frame["low"] <= frame["open"])
            & (frame["low"] <= frame["close"])
            & (frame["high"] >= frame["low"])
        )).sum()
    )
    invalid_volume_count = int((frame["volume"] < 0).sum())
    return {
        "row_count": int(len(frame)),
        "missing_count": missing_count,
        "duplicate_count": duplicate_count,
        "invalid_ohlc_count": invalid_ohlc_count,
        "invalid_volume_count": invalid_volume_count,
    }
```

    missing_count = int(frame[required].isna().any(axis=1).sum())
    duplicate_count = int(frame.duplicated(subset=["symbol", "timestamp"]).sum())
    invalid_ohlc_count = int(
        (~((frame["high"] >= frame["open"])
           & (frame["high"] >= frame["close"])
           & (frame["low"] <= frame["open"])
           & (frame["low"] <= frame["close"])
           & (frame["high"] >= frame["low"]))
        ).sum()
    )
    invalid_volume_count = int((frame["volume"] < 0).sum())
    return {
        "row_count": int(len(frame)),
        "missing_count": missing_count,
        "duplicate_count": duplicate_count,
        "invalid_ohlc_count": invalid_ohlc_count,
        "invalid_volume_count": invalid_volume_count,
    }
```

Cú pháp quan trọng — `frame[required].isna().any(axis=1)`:
- `.isna()` → DataFrame boolean (cùng shape).
- `.any(axis=1)` → Series 1 chiều, `True` ở dòng có ít nhất 1 NaN.
- `.sum()` → đếm số `True`.

---

## 7. Nguồn dữ liệu và cơ chế failover

### 7.1. Tại sao em cần nhiều provider?

Không có nguồn dữ liệu chứng khoán nào hoàn hảo 100%:

| Provider | Ưu điểm | Nhược điểm |
|----------|---------|------------|
| **yfinance** | Miễn phí, không cần API key, lookback 10+ năm cho US stock | Thỉnh thoảng bị block, không có cổ phiếu Việt Nam |
| **SSI iBoard** | Dữ liệu HOSE/HNX/UPCOM chính xác, free tier | API riêng, có thể thay đổi |
| **Finnhub** | Global + Việt Nam, có sentiment/news | Free tier: 60 req/min, lookback hạn chế |
| **Alpha Vantage** | US stocks, forex, crypto | Free tier: 25 req/ngày, chậm |
| **Web Scraper (CafeF)** | Backup khi API lỗi | Có thể bị chặn, cần parse HTML |

### 7.2. DataSourceFactory – Chọn provider bằng biến môi trường

Em dùng factory pattern để **chọn provider không cần sửa code**:

```bash
# .env
DATA_SOURCE=yfinance          # US stocks
DATA_SOURCE=ssi_vn            # Cổ phiếu Việt Nam
DATA_SOURCE=multi_source      # Failover tự động
```

Factory kiểm tra API key trước khi khởi tạo provider. Ví dụ: nếu `DATA_SOURCE=finnhub` nhưng `.env` không có `FINNHUB_API_KEY` → raise `DataSourceError` ngay, không chạy âm thầm rồi fail ở giữa chừng.

### 7.3. MultiSourceProvider – Failover tự động

Đây là cơ chế **quan trọng nhất** đảm bảo hệ thống không chết khi một nguồn lỗi:

```python
adapter = MultiSourceProvider([
    "yfinance",       # Thử trước – lookback rộng nhất
    "finnhub",        # Backup 1
    "yfinance_direct", # Backup 2
    "alpha_vantage",  # Backup cuối cùng
])
```

**Cách hoạt động:**
1. Thử `yfinance` → nếu trả về DataFrame không rỗng → done.
2. Nếu `yfinance` lỗi hoặc trả rỗng → thử `finnhub`.
3. Nếu `finnhub` lỗi → thử `yfinance_direct`.
4. Nếu tất cả đều lỗi → raise `DataSourceError`.

Em không để chương trình chạy tiếp khi tất cả nguồn đều lỗi — đúng hơn là trả về dữ liệu sai (sai còn tai hại hơn không có).

### 7.4. Tại sao em tách `finnhub` vs `yfinance_direct` vs `yfinance`?

- `yfinance` (package): dùng thư viện Python chính thức, đơn giản, xử lý split/dividend tự động.
- `yfinance_direct`: gọi REST API Yahoo Finance trực tiếp bằng `requests`, không cần thư viện `yfinance`. Dùng khi thư viện bị lỗi hoặc không cài được.
- `finnhub`: API riêng, rate limit thấp, cần API key.

### 7.5. Code của từng provider – đọc nhanh

#### 7.5.1. `YFinancePythonProvider` – provider chính cho US

```startLine:54:130:backend/app/data_sources/yfinance_python_provider.py
class YFinancePythonProvider(StockDataProvider):
    """High-level Yahoo Finance provider using the ``yfinance`` package."""

    source_name = "yfinance_python"

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or settings.yfinance_timeout or 30
        self._yf: Any | None = None

    @property
    def yf(self) -> Any:
        if self._yf is None:
            self._yf = _safe_yfinance_import()
        return self._yf
```

- `@property yf`: dynamic attribute. Lần đầu truy cập mới import `yfinance`. Nếu package lỗi → `_safe_yfinance_import()` raise `DataSourceError`.
- Lazy import: giúp app không crash nếu user không cài `yfinance`.

```startLine:76:120:backend/app/data_sources/yfinance_python_provider.py
    @staticmethod
    def _normalize(df: pd.DataFrame, symbol: str, source: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        frame = df.copy()

        # Flatten multi-index (yfinance >=0.2.40 returns columns as MultiIndex)
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [str(col[0]) for col in frame.columns]

        if frame.index.tzinfo is not None:
            frame.index = frame.index.tz_convert("UTC")
        else:
            frame.index = frame.index.tz_localize("UTC")

        frame = frame.reset_index().rename(columns={"index": "timestamp", "Date": "timestamp"})
        ...
        frame["symbol"] = symbol.upper()
        frame["source"] = source
        frame["ingestion_time"] = pd.Timestamp.now(tz="UTC")
        ...
        return frame[OHLCV_COLUMNS]
```

**Quan trọng:**
- `pd.Timestamp.now(tz="UTC")`: timezone-aware timestamp — bắt buộc cho partition theo year/month.
- `frame.index.tz_localize("UTC")`: nếu index **không có** timezone → gắn UTC. Ngược lại `tz_convert("UTC")` nếu đã có.
- Cuối cùng `frame[OHLCV_COLUMNS]` chỉ giữ đúng 10 cột chuẩn → Bronze chỉ thấy schema thống nhất.

#### 7.5.2. `FinnhubProvider` – cần API key

```startLine:47:80:backend/app/data_sources/finnhub_provider.py
class FinnhubProvider(StockDataProvider):
    """Fetch OHLCV data via Finnhub API."""

    source_name = "finnhub"

    BASE_URL = "https://finnhub.io/api/v1"

    INTERVAL_MAP: dict[str, str] = {
        "1d": "D",
        "1h": "60",
        "15m": "15",
        "5m": "5",
        "1m": "1",
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = (
            api_key
            or getattr(settings, "finnhub_api_key", None)
            or ""
        )
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "stock-lakehouse-ai/1.0 (+https://finnhub.io)"}
        )

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key) and self.api_key != "demo"
```

- `BASE_URL = "..."` và `INTERVAL_MAP`: class-level constant — dùng chung cho mọi instance.
- `self.session = requests.Session()`: tạo 1 session để **tái sử dụng** TCP connection (HTTP keep-alive). Nhanh hơn gọi `requests.get(...)` mỗi lần.
- `getattr(settings, "finnhub_api_key", None)`: an toàn khi settings có thể không có key này (default `None`).

```startLine:82:118:backend/app/data_sources/finnhub_provider.py
    def _request(self, endpoint: str, params: dict | None = None) -> dict:
        if not self.has_credentials:
            raise DataSourceError("Finnhub API key is not configured. ...")
        params = params.copy() if params else {}
        params["token"] = self.api_key
        try:
            response = self.session.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=30)
        except requests.exceptions.RequestException as exc:
            raise DataSourceError(f"Finnhub request failed: {exc}") from exc

        if response.status_code == 401 or response.status_code == 403:
            raise DataSourceError("Finnhub authentication failed. Check FINNHUB_API_KEY in .env.")
        if response.status_code == 429:
            raise DataSourceError("Finnhub rate limit exceeded (60 req/min on Free tier). Wait ~60s and retry.")

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise DataSourceError(f"Finnhub HTTP error: {exc}") from exc
        ...
```

- Phân biệt rõ 401/403 (sai key), 429 (rate limit), HTTPError (server bug) → message riêng.
- `raise X from Y`: trong Python, `from` giữ nguyên **original traceback** để debug — không mất context.

#### 7.5.3. `SSIVNProvider` – cổ phiếu Việt Nam

```startLine:60:100:backend/app/data_sources/ssi_vn_provider.py
class SSIVNProvider(StockDataProvider):
    """Fetch historical OHLCV from SSI iBoard for VN-listed tickers."""

    source_name = "ssi_vn"
    DEFAULT_URL = "https://iboard-api.ssi.com.vn/statistics/charts/history"
    DEFAULT_TIMEOUT = 20

    def __init__(self, timeout: int | None = None, rate_limit_sleep: float = 0.5) -> None:
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.rate_limit_sleep = rate_limit_sleep
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
            "Origin": "https://iboard.ssi.com.vn",
            "Referer": "https://iboard.ssi.com.vn/",
        })
```

- `User-Agent` giả trình duyệt thật → tránh bị server chặn (rate limit).
- `Origin`/`Referer`: một số API check CSRF cơ bản — gửi đúng Origin giúp không bị 403.

```startLine:120:160:backend/app/data_sources/ssi_vn_provider.py
    @staticmethod
    def _normalize(data: dict, symbol: str) -> pd.DataFrame:
        t = data["t"]
        o = data["o"]
        h = data["h"]
        l = data["l"]
        c = data["c"]
        v = data.get("v") or [0] * len(t)

        # SSI returns prices in *thousands* of VND. Convert to absolute VND.
        records: list[dict] = []
        for i, ts in enumerate(t):
            try:
                open_p = float(o[i]) * 1000.0
                ...
            except (TypeError, ValueError):
                continue

            if close_p <= 0:
                continue

            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            records.append({"timestamp": dt, "open": open_p, ...})
        ...
```

- `data["v"] or [0] * len(t)`: nếu `v` không tồn tại → tạo list 0 cùng độ dài. Tránh IndexError.
- `*1000.0`: SSI trả giá theo **đơn vị nghìn VND**, em quy đổi sang VND tuyệt đối để thống nhất với mọi provider khác.
- `data.get("v") or ...`: `dict.get(key, default)` trả default nếu key không có. Toán tử `or` thêm fallback khi value là `None`.

---

## 8. Tầng lưu trữ – Tại sao tách Storage Backend?

### 8.1. Vấn đề em gặp phải

Lúc đầu em viết code ghi file thẳng vào MinIO. Khi test local, muốn chạy nhanh với filesystem thường thì phải sửa lại toàn bộ code. Em quyết định tách ra interface `StorageBackend`:

```python
class StorageBackend(ABC):
    def write_parquet(self, layer, path, frame) -> str: ...
    def read_parquet(self, layer, path) -> pd.DataFrame: ...
    def read_prefix(self, layer, prefix) -> pd.DataFrame: ...
    def exists(self, layer, path) -> bool: ...
    def write_json(self, layer, path, payload) -> dict: ...
```

Hai implementation hiện tại:
- `LocalStorageBackend`: ghi vào thư mục `backend/data/{bronze,silver,gold}/`.
- `MinioStorageBackend`: ghi vào MinIO bucket `lakehouse/`.

### 8.2. Factory chọn backend tự động

```python
def get_storage_backend() -> StorageBackend:
    if settings.storage_backend == "minio":
        try:
            backend = MinioStorageBackend()
            if backend.health()["available"]:
                return backend
        except Exception:
            pass  # Fallback
    return LocalStorageBackend()  # Mặc định local
```

**Quy tắc:**
- Dev local (không có MinIO): dùng LocalStorageBackend.
- Prod/Demo (MinIO chạy): dùng MinioStorageBackend.
- MinIO không khả dụng: **tự động fallback** về LocalStorageBackend mà không crash.

### 8.3. Lợi ích của thiết kế này

| Tình huống | Không có abstraction | Có StorageBackend |
|------------|---------------------|-------------------|
| Dev local | Phải sửa code để dùng filesystem | Tự động dùng LocalStorage |
| Demo với MinIO | Phải sửa code | Đổi 1 biến môi trường |
| MinIO lỗi giữa chừng | Crash | Fallback tự động |
| Chuyển sang AWS S3 | Viết lại toàn bộ code | Thêm 1 class `S3StorageBackend` |

### 8.4. Code của StorageBackend

#### 8.4.1. Abstract contract

```startLine:1:64:backend/app/lakehouse/storage_base.py
"""Abstract object/file storage used by the lakehouse."""

from __future__ import annotations

from abc import ABC, abstractmethod
from io import BytesIO

import pandas as pd


class StorageBackend(ABC):
    """Read/write Parquet datasets for Bronze, Silver, and Gold."""

    backend_name: str = "abstract"

    @abstractmethod
    def write_parquet(self, layer: str, relative_path: str, frame: pd.DataFrame) -> str:
        """Persist a DataFrame as Parquet and return the storage path."""

    @abstractmethod
    def read_parquet(self, layer: str, relative_path: str) -> pd.DataFrame:
        """Read a single Parquet object."""

    @abstractmethod
    def read_prefix(self, layer: str, prefix: str) -> pd.DataFrame:
        """Read and concatenate all Parquet files under a prefix."""

    @abstractmethod
    def list_objects(self, layer: str, prefix: str = "") -> list[str]:
        """List object keys under a prefix."""

    @abstractmethod
    def exists(self, layer: str, relative_path: str) -> bool:
        """Return True if the object exists."""

    @abstractmethod
    def write_json(self, layer: str, relative_path: str, payload: dict) -> str:
        """Persist a JSON metadata document."""

    @abstractmethod
    def read_json(self, layer: str, relative_path: str) -> dict:
        """Read a JSON metadata document."""

    @abstractmethod
    def count_objects(self, layer: str, prefix: str = "") -> int:
        """Count objects under a prefix."""

    def health(self) -> dict[str, str | bool]:
        return {"backend": self.backend_name, "available": True}


def dataframe_to_parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_parquet(buffer, engine="pyarrow", index=False)
    return buffer.getvalue()


def parquet_bytes_to_dataframe(payload: bytes) -> pd.DataFrame:
    return pd.read_parquet(BytesIO(payload), engine="pyarrow")
```

**Giải thích:**
- 8 method `@abstractmethod` — bất kỳ class nào muốn làm `StorageBackend` phải implement đủ 8 cái.
- `health()` không abstract — đã có default trả `{"available": True}`.
- 2 helper `dataframe_to_parquet_bytes` / `parquet_bytes_to_dataframe`: chuyển đổi qua lại giữa DataFrame và bytes Parquet. Dùng cho MinIO (cần stream bytes qua HTTP).

#### 8.4.2. `LocalStorageBackend` – filesystem

```startLine:1:95:backend/app/lakehouse/local_storage.py
class LocalStorageBackend(StorageBackend):
    """Store lakehouse datasets under backend/data."""

    backend_name = "local"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.data_root_path
        for folder in LAYER_FOLDERS.values():
            (self.root / folder).mkdir(parents=True, exist_ok=True)

    def _path(self, layer: str, relative_path: str) -> Path:
        if layer not in LAYER_FOLDERS:
            raise StorageError(f"Unknown lakehouse layer: {layer}")
        return self.root / LAYER_FOLDERS[layer] / relative_path.replace("\\", "/")

    def write_parquet(self, layer: str, relative_path: str, frame: pd.DataFrame) -> str:
        path = self._path(layer, relative_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, engine="pyarrow", index=False)
        except Exception as exc:
            raise StorageError(f"Failed to write parquet {path}: {exc}") from exc
        return str(path)

    def read_prefix(self, layer: str, prefix: str) -> pd.DataFrame:
        base = self._path(layer, prefix)
        files = sorted(base.rglob("*.parquet")) if base.exists() else []
        if not files:
            return pd.DataFrame()
        frames = [pd.read_parquet(file, engine="pyarrow") for file in files]
        return pd.concat(frames, ignore_index=True)
```

**Quan trọng:**
- `(self.root / folder).mkdir(parents=True, exist_ok=True)`: tạo folder nếu chưa có. `parents=True` tạo cả folder cha, `exist_ok=True` không lỗi nếu đã tồn tại.
- `Path.rglob("*.parquet")`: **recursive glob** — tìm mọi file `.parquet` trong cây con.
- `relative_path.replace("\\", "/")`: ép dùng `/` thay vì `\` (Windows) để code cross-OS.

#### 8.4.3. `MinioStorageBackend` – S3-compatible

```startLine:30:60:backend/app/lakehouse/minio_storage.py
class MinioStorageBackend(StorageBackend):
    """Store lakehouse datasets in MinIO buckets."""

    backend_name = "minio"

    def __init__(self) -> None:
        try:
            from minio import Minio
        except ImportError as exc:
            raise StorageError("minio package is not installed.") from exc
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._ensure_buckets()

    def _ensure_buckets(self) -> None:
        try:
            for bucket in set(LAYER_BUCKETS.values()):
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    logger.info("Created MinIO bucket %s", bucket)
        except Exception as exc:
            raise StorageError(f"Cannot initialize MinIO buckets: {exc}") from exc
```

- `from minio import Minio`: lazy import. Nếu thiếu package → StorageError rõ ràng.
- `_ensure_buckets()`: kiểm tra + tạo 5 bucket (`stock-bronze`, `stock-silver`, `stock-gold`, `stock-models`, `stock-backtests`).

```startLine:108:140:backend/app/lakehouse/minio_storage.py
    def health(self) -> dict[str, str | bool]:
        try:
            self.client.list_buckets()
            return {"backend": self.backend_name, "available": True}
        except Exception as exc:
            logger.warning("MinIO health check failed: %s", exc)
            return {"backend": self.backend_name, "available": False}

    def _put_bytes(self, layer: str, relative_path: str, payload: bytes, content_type: str) -> str:
        bucket = self._bucket(layer)
        try:
            self.client.put_object(
                bucket, relative_path, BytesIO(payload),
                length=len(payload), content_type=content_type,
            )
        except Exception as exc:
            raise StorageError(f"MinIO put failed for {relative_path}: {exc}") from exc
        return f"{bucket}/{relative_path}"
```

- `BytesIO(payload)`: chuyển `bytes` thành file-like object (cần cho MinIO SDK).
- `length=len(payload)`: bắt buộc truyền size khi dùng `BytesIO` (không có file thật).

#### 8.4.4. Factory – fallback khi MinIO chết

```startLine:1:35:backend/app/lakehouse/storage_factory.py
def get_storage_backend() -> StorageBackend:
    """Return MinIO storage when configured and healthy, otherwise local files."""
    if settings.storage_backend == "minio":
        try:
            from app.lakehouse.minio_storage import MinioStorageBackend

            backend = MinioStorageBackend()
            health = backend.health()
            if health.get("available"):
                logger.info("Using MinIO storage backend.")
                return backend
            logger.warning("MinIO is configured but unavailable. Falling back to local storage.")
        except Exception as exc:
            logger.warning("MinIO initialization failed (%s). Falling back to local storage.", exc)
    logger.info("Using local filesystem storage backend.")
    return LocalStorageBackend()
```

**Cú pháp quan trọng:**
- `try ... except Exception: ...`: nuốt mọi exception khi khởi tạo MinIO. Đây là **defensive programming** — nếu MinIO chưa start, container chưa ready, network lỗi — vẫn fallback an toàn.
- `settings.storage_backend` đọc từ `.env` (`STORAGE_BACKEND=minio` hoặc `local`).

---

## 9. Apache Iceberg – Vì sao chọn Iceberg thay vì Delta Lake?

### 9.1. So sánh em đã cân nhắc

| Tiêu chí | Delta Lake | Apache Iceberg | Em chọn |
|----------|-----------|----------------|---------|
| **Nhà cung cấp** | Databricks (lock-in cao) | Open-source (AWS, Snowflake, StarRocks đều hỗ trợ) | Iceberg |
| **Cloud** | Cần Databricks hoặc Spark + cloud storage | Chạy local với MinIO hoặc lên cloud (S3, GCS, Azure) | Iceberg |
| **Time travel** | Có | Có | Cả hai |
| **Schema evolution** | Có | Có (đầy đủ hơn) | Cả hai |
| **Partition evolution** | Không | Có (đổi partition scheme không rewrite data) | Iceberg |
| **ACID commit** | Có | Có | Cả hai |
| **REST Catalog** | Không có sẵn | Có (Iceberg REST Catalog) | Iceberg |

### 9.2. Lý do quyết định

Em chọn Iceberg vì 2 lý do chính:

**1. Open-source hoàn toàn, không bị lock-in:**
Delta Lake gắn chặt với hệ sinh thái Databricks. Nếu em sau này muốn chuyển từ MinIO lên AWS S3 hoặc Snowflake, Delta Lake yêu cầu cấu hình khác. Iceberg được nhiều engine hỗ trợ (Spark, Flink, Trino, DuckDB, Snowflake, StarRocks) - đây là **điểm mấu chốt** cho một đồ án nghiên cứu muốn trình bày tính mở rộng.

**2. Iceberg REST Catalog chạy bằng Docker 1 lệnh:**
Em dùng `tabulario/iceberg-rest` container — không cần Nessie hay HMS phức tạp. Đủ để demo time travel, schema evolution trong thesis mà không tốn effort vận hành.

### 9.3. Các tính năng Iceberg em dùng (và sẽ dùng)

**Time travel:**
```python
# Đọc dữ liệu như 3 ngày trước
df = manager.read_bronze("VCB", as_of_timestamp="3d")

# Xem lịch sử thay đổi
snapshots = manager.list_snapshots("bronze")
# [{snapshot_id: 1, operation: "append"}, {snapshot_id: 2, operation: "append"}]

# Rollback về phiên bản cũ nếu bug
manager.rollback_to_snapshot("silver", snapshot_id=1)
```

**Schema evolution:**
```python
# Thêm cột mới mà không cần rewrite toàn bộ data
# Cần thêm: emotional_sentiment, institutional_flow
# Chạy ALTER TABLE → Iceberg tự migrate metadata
```

**Hidden partitioning:**
```python
# Em partition theo month nhưng query theo ngày
# Iceberg tự hiểu filter "WHERE timestamp = '2024-03'" thuộc partition month=3
# Không cần em ghi rõ partition trong query
```

### 9.4. Vì sao dùng MinIO thay vì S3 thật?

MinIO là S3-compatible object storage chạy **100% local**:

- **Chi phí: 0 đồng** (S3 thật có phí theo GB).
- **Không cần internet** (S3 thật cần network).
- **API hoàn toàn tương thích S3** (bất kỳ tool S3 nào đều dùng được với MinIO).
- **Docker 1 lệnh**: `docker compose up minio` → xong.

Khi em muốn lên production thực sự, chỉ cần đổi endpoint từ `localhost:9000` sang `s3.amazonaws.com` và thêm credentials. Không phải sửa code nào khác.

### 9.5. Code `IcebergManager` – quan trọng nhất là schema

File `backend/app/lakehouse/iceberg_manager.py` (745 dòng).

#### 9.5.1. Schema Iceberg – khác với Parquet plain

```startLine:101:175:backend/app/lakehouse/iceberg_manager.py
BRONZE_SCHEMA = Schema(
    schema_id=1,
    identifier_field_ids=[1, 2],   # (symbol, timestamp) là primary key
    fields=(
        NestedField(field_id=1, name="symbol", field_type=StringType(), required=True, doc="Ticker symbol"),
        NestedField(field_id=2, name="timestamp", field_type=TimestampType(), required=True, doc="OHLCV bar timestamp (UTC)"),
        NestedField(field_id=3, name="open", field_type=DoubleType(), required=True, doc="Opening price"),
        NestedField(field_id=4, name="high", field_type=DoubleType(), required=True, doc="Highest price"),
        NestedField(field_id=5, name="low", field_type=DoubleType(), required=True, doc="Lowest price"),
        NestedField(field_id=6, name="close", field_type=DoubleType(), required=True, doc="Closing price"),
        NestedField(field_id=7, name="adj_close", field_type=DoubleType(), required=True, doc="Adjusted close"),
        NestedField(field_id=8, name="volume", field_type=DoubleType(), required=True, doc="Trading volume"),
        NestedField(field_id=9, name="source", field_type=StringType(), required=False, doc="Data source provider"),
        NestedField(field_id=10, name="ingestion_time", field_type=TimestampType(), required=True, doc="When record was ingested"),
    ),
)

SILVER_SCHEMA = Schema(
    schema_id=1, identifier_field_ids=[1, 2],
    fields=(
        ...
        NestedField(field_id=11, name="data_quality", field_type=StringType(), required=False, doc="Quality status"),
    ),
)

GOLD_SCHEMA = Schema(
    schema_id=1, identifier_field_ids=[1, 2],
    fields=(
        ...
        NestedField(field_id=20, name="sma_20", field_type=DoubleType(), required=False, doc="20-day SMA"),
        NestedField(field_id=24, name="rsi_14", field_type=DoubleType(), required=False, doc="14-day RSI"),
        ...
        NestedField(field_id=40, name="return_1d", field_type=DoubleType(), required=False, doc="Next 1-day return (target)"),
        NestedField(field_id=42, name="direction_1d", field_type=IntegerType(), required=False, doc="1 if price up tomorrow, 0 otherwise"),
    ),
)
```

**Khác biệt với Parquet:**
- Mỗi field có `field_id` immutable. Thêm cột mới → Iceberg tự cấp id mới, không phá schema cũ.
- `identifier_field_ids=[1, 2]`: Iceberg dùng để xác định "primary key" cho dedup / upsert.
- `required=True/False`: bắt buộc/không bắt buộc (Iceberg enforce ở write time).

#### 9.5.2. Catalog kết nối Iceberg REST + MinIO

```startLine:186:228:backend/app/lakehouse/iceberg_manager.py
def get_iceberg_catalog() -> Catalog:
    settings = get_settings()
    catalog_uri = settings.ICEBERG_CATALOG_URI or DEFAULT_CATALOG_URI

    return pyiceberg.catalog.load_catalog(
        "rest",
        **{
            "uri": catalog_uri,
            "s3.endpoint": "http://localhost:9000",
            "s3.access-key-id": "minioadmin",
            "s3.secret-access-key": "minioadmin",
        },
    )


TABLE_BRONZE = "lakehouse.bronze_ohlcv"
TABLE_SILVER = "lakehouse.silver_ohlcv"
TABLE_GOLD = "lakehouse.gold_features"
```

- `load_catalog("rest", **kwargs)`: PyIceberg client connect tới Iceberg REST Catalog (`tabulario/iceberg-rest:0.9.0` chạy ở port 8181).
- `s3.endpoint=http://localhost:9000`: trỏ tới MinIO. Iceberg sẽ ghi file Parquet vào bucket MinIO.

#### 9.5.3. Tạo bảng + partition spec

```startLine:255:295:backend/app/lakehouse/iceberg_manager.py
    def create_bronze_table(self, if_not_exists: bool = True) -> Table:
        try:
            table = self.catalog.create_table(
                identifier=TABLE_BRONZE,
                schema=BRONZE_SCHEMA,
                partition_spec=pyiceberg.table._parse_partition_spec(
                    BRONZE_SCHEMA,
                    [("symbol", "identity"), ("timestamp", "month")],
                ),
                properties={
                    "format": "parquet",
                    "write.parquet.compression-codec": "zstd",
                },
            )
            ...
```

- Partition spec `[("symbol", "identity"), ("timestamp", "month")]`: hash theo `symbol`, bucket theo `month` của timestamp. Query `WHERE symbol='AAPL' AND timestamp BETWEEN ...` sẽ tự prune các partition không liên quan.
- `write.parquet.compression-codec=zstd`: nén Zstandard — tỉ lệ nén tốt hơn gzip, CPU nhanh hơn.

#### 9.5.4. Time travel – đọc dữ liệu quá khứ

```startLine:486:505:backend/app/lakehouse/iceberg_manager.py
    def read_bronze(
        self,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        as_of_snapshot_id: int | None = None,
        as_of_timestamp: str | None = None,
    ) -> pd.DataFrame:
        return self._read_table(
            "bronze",
            symbol=symbol, start=start, end=end,
            as_of_snapshot_id=as_of_snapshot_id,
            as_of_timestamp=as_of_timestamp,
        )
```

```startLine:548:610:backend/app/lakehouse/iceberg_manager.py
    def _read_table(self, layer, symbol, start, end, as_of_snapshot_id, as_of_timestamp):
        table = self.load_table(layer)

        if as_of_snapshot_id:
            plan = table.scan(snapshot_id=as_of_snapshot_id)
        elif as_of_timestamp:
            ts = self._parse_timestamp(as_of_timestamp)
            plan = table.scan(as_of_timestamp=ts.isoformat())
        else:
            plan = table.scan()

        ...
```

- `table.scan(snapshot_id=...)`: chỉ định đúng snapshot id để đọc.
- `table.scan(as_of_timestamp=...)`: truy vấn "như tại thời điểm T". Hữu ích khi debug — "VCB 3 ngày trước nhìn thế nào?".

```startLine:617:655:backend/app/lakehouse/iceberg_manager.py
    def list_snapshots(self, layer) -> list[dict]:
        table = self.load_table(layer)
        snapshots = []
        for snap in table.history():
            snapshots.append({
                "snapshot_id": snap.snapshot_id,
                "parent_id": snap.parent_id,
                "timestamp": snap.timestamp_ms,
                "operation": snap.operation.value if hasattr(snap.operation, "value") else str(snap.operation),
            })
        return snapshots

    def rollback_to_snapshot(self, layer, snapshot_id) -> dict:
        table = self.load_table(layer)
        table.rollback(snapshot_id=snapshot_id)
        return {"layer": layer, "rolled_back_to": snapshot_id, ...}
```

- `table.history()`: trả list `Snapshot` objects — mỗi lần commit sẽ có 1 entry.
- `rollback_to_snapshot`: "undo" bảng về 1 phiên bản cũ. Iceberg tự giữ snapshot cũ làm garbage.

---

## 10. Khó khăn đã gặp và cách xử lý

| Khó khăn | Chi tiết | Cách em xử lý |
|----------|----------|---------------|
| **Dữ liệu thiếu phiên, trùng timestamp, OHLC không hợp lệ** | Yahoo Finance có ngày không có dữ liệu (market holiday), SSI trả sai timestamp timezone | Validate tại Silver, ghi bản ghi lỗi vào `_errors/`, giữ dữ liệu gốc ở Bronze |
| **Nguồn dữ liệu không ổn định** | Yahoo Finance block request, rate limit Finnhub | `MultiSourceProvider` failover tự động, fallback chain theo interval |
| **Cổ phiếu Việt Nam không có trên yfinance** | yfinance không hỗ trợ HOSE/HNX | Tích hợp thêm `SSIVNProvider` (SSI iBoard API) và `web_scraper_provider` (CafeF) |
| **Spark cluster khởi động chậm** | Mỗi lần dev nhỏ phải chờ Spark khởi động 15–30s rất bất tiện, lại thêm 1 service Docker phải vận hành | Bỏ Spark, dùng Pandas làm engine chính cho Silver transform (data hiện tại ~120k rows, Pandas xử lý thoải mái). Iceberg vẫn giữ vì đã có REST catalog tích hợp sẵn với Pandas. |
| **Phạm vi công nghệ rộng (Kafka, Iceberg, ML, DL, React, AI)** | Solo thesis, thời gian có hạn | Ưu tiên prototype end-to-end, mỗi module chỉ làm phần cốt lõi, đầu ra rõ ràng |
| **Rủi ro look-ahead leakage** | Dùng future data trong training → model "nhìn thấy đáp án" | Chia train/test theo thời gian, dùng `shift()` đúng chiều, không dùng `train_test_split` ngẫu nhiên |
| **Kafka ZooKeeper phức tạp** | ZK cũ đã deprecated, cấu hình phức tạp cho solo | Dùng Kafka KRaft mode (không cần ZooKeeper) từ Kafka 3.3+ |

---

## 11. Phần chưa hoàn thành và kế hoạch tuần 3–4

### 11.1. Những gì chưa làm xong

Theo kế hoạch đã cam kết với thầy, các phần dưới đây mới ở mức khởi tạo hoặc thiết kế:

- Chưa train và so sánh Linear Regression, ARIMA, LSTM đầy đủ.
- Chưa hoàn thiện backtesting (Total Return, Sharpe Ratio, Win Rate, Maximum Drawdown).
- AI Agent mới thiết kế tool skeleton, chưa tích hợp thực sự.
- React/FastAPI mới ở mức skeleton, chưa kết nối Gold dataset.

> Phần này viết theo kế hoạch ban đầu (tuần 1-2). Tại thời điểm cập nhật 01/10/2026, toàn bộ các mục "chưa hoàn thành" đã được giải quyết: Linear Regression / ARIMA / LSTM đã train xong và so sánh qua API `/forecast/compare`; backtest đã có Total Return / Sharpe / Win Rate / Max Drawdown / Profit Factor; AI Agent đã tích hợp Gemini Free và route 14+ tools; React frontend đã kết nối đầy đủ Gold dataset. Xem [`docs/PROGRESS.md`](PROGRESS.md) để biết trạng thái mới nhất.

### 11.2. Kế hoạch tuần 3

| Ngày | Hạng mục | Nội dung |
|------|----------|---------|
| Tuần 3 T2–T3 | Gold dataset | Verify MA/RSI/MACD/Bollinger trên 5–10 mã VN, so sánh với chart thực |
| Tuần 3 T2–T3 | Pipeline DAG | Đưa Bronze → Silver → Gold vào schedule, thêm logging |
| Tuần 3 T4 | Indicator verify | Vẽ chart để đối chiếu với TradingView, chứng minh tính đúng |
| Tuần 3 T5 | Cron scheduler | `scripts/schedule_batch.py` chạy ingest + pipeline hàng ngày (cron-like) |

### 11.3. Kế hoạch tuần 4

| Ngày | Hạng mục | Nội dung |
|------|----------|---------|
| Tuần 4 T2–T3 | Baseline model | Train Linear Regression và ARIMA, đánh giá MAE, RMSE, MAPE |
| Tuần 4 T2–T3 | LSTM | Chuẩn hóa dữ liệu, tạo sequence, train trên 1–2 mã |
| Tuần 4 T4 | FastAPI | Expose endpoint truy vấn Gold + indicators, chuẩn bị cho React/Agent |
| Tuần 4 T5 | Documentation | Hoàn thiện báo cáo, sơ đồ kiến trúc, bằng chứng chạy thử |

### 11.4. Mục tiêu đầu ra sau 04 tuần

- ✅ Luồng dữ liệu Bronze → Silver → Gold hoàn chỉnh.
- ✅ Dataset Gold với bộ feature kỹ thuật đầy đủ.
- ✅ Ít nhất 1 kết quả baseline forecasting (Linear Regression hoặc ARIMA).
- ✅ API cơ bản phục vụ truy vấn dữ liệu và chỉ báo.
- ✅ Tài liệu kiến trúc, pipeline và bằng chứng chạy thử cho báo cáo khóa luận.

---

## 12. Hướng dẫn demo cho thầy

### 12.0. Chuẩn bị trước khi demo (chạy 1 lần)

```powershell
# 1. Khởi động Docker (nếu chưa chạy)
docker compose up -d

# 2. Cài dependencies
cd backend
pip install -r requirements.txt

# 3. Chạy 1 mã qua pipeline đầy đủ (mất ~30 giây)
python -c "
from app.pipelines import run_symbol_pipeline
r = run_symbol_pipeline('AAPL')
print('Status:', r['status'])
print('Records:', r['records_processed'])
print('Quality:', r['quality']['quality_status'])
"

# 4. Bật FastAPI
uvicorn app.main:app --reload
# Mở http://localhost:8000/docs để xem API
```

---

### Demo 1 – Chứng minh môi trường chạy được (1 phút)

**Mục tiêu:** Thầy thấy 4 service đều hoạt động, không có "chết container" nào.

```powershell
docker compose ps
```

**Giải thích cho thầy:** "Đây là toàn bộ môi trường chạy trong Docker. **MySQL** lưu metadata (lịch sử pipeline / model / backtest / chat). **MinIO** là object storage S3-compatible, chứa Bronze/Silver/Gold. **Iceberg REST Catalog** quản lý schema bảng, hỗ trợ time-travel. **Kafka** làm backbone streaming cho tuần 5 trở đi (Finnhub WebSocket → Kafka → Consumer → Lakehouse)."

---

### Demo 2 – Chứng minh Bronze có dữ liệu thật (2 phút)

**Bước 1:** Mở MinIO console → <http://localhost:9001> (user: `minioadmin`, pass: `minioadmin`) → bucket `stock-bronze` → `symbol=AAPL/year=2026/month=10/`.

**Bước 2:** Chạy lệnh đọc trực tiếp từ backend:
```powershell
cd backend
python -c "from app.lakehouse import BronzeLayer; b=BronzeLayer(); df=b.read('AAPL'); print(df.shape); print(df.head())"
```

**Giải thích cho thầy:** "Đây là dữ liệu AAPL crawl từ yfinance, giữ nguyên schema gốc. Mỗi record có `source=yfinance_python` và `ingestion_time` để em truy vết lại."

---

### Demo 3 – Chạy Silver transform (2 phút)

**Mục tiêu:** Thầy thấy pipeline làm sạch dữ liệu có kiểm soát.

```powershell
cd backend
python -c "
from app.lakehouse import BronzeLayer, SilverLayer
b = BronzeLayer()
s = SilverLayer()
df_bronze = b.read('AAPL')
df_silver, report = s.transform(df_bronze)
print('Source count:', report['source_count'])
print('Valid count:', report['record_count'])
print('Invalid OHLC:', report['invalid_ohlc_count'])
print('Duplicates:', report['duplicate_count'])
print('Quality:', report['quality_status'])
"
```

**Giải thích cho thầy:** "Nguồn có X records, Y records hợp lệ. Em ghi riêng vào `_errors/` chứ không xóa âm thầm. Đây là bằng chứng cho thấy Silver xử lý có kiểm soát."

---

### Demo 4 – Show dataset Gold với features (2 phút)

**Mục tiêu:** Thầy thấy Gold có đầy đủ features cho ML/DL.

```powershell
cd backend
python -c "
from app.lakehouse import GoldLayer, SilverLayer
s = SilverLayer()
g = GoldLayer()
df_silver = s.read('AAPL')
df_gold = g.transform(df_silver)
print('Columns:', len(df_gold.columns))
print(df_gold.columns.tolist())
print()
print('Last 5 rows (key columns):')
print(df_gold[['timestamp','close','sma_5','sma_20','rsi_14','macd','signal','bb_upper','bb_lower','return_1d','target_direction_next']].tail(5))
"
```

**Giải thích cho thầy:** "Tất cả indicators đều được tính sẵn. `return_1d` là target cho model (dùng `shift()` đúng chiều, không có leakage). `sma_5`, `sma_20`, `rsi_14`, `macd` là input features. 50 dòng đầu có NaN vì rolling window — đây là normal, model tự skip."

---

### Demo 5 – Chứng minh truy vết được (1 phút)

```powershell
cd backend
type backend\data\bronze\symbol=AAPL\_lineage.json
# Hoặc: cat backend/data/bronze/symbol=AAPL/_lineage.json (WSL)
```

**Giải thích cho thầy:** "Mỗi lần ingest đều ghi `_lineage.json` với đầy đủ metadata. Em biết chính xác: ingest lúc nào, bao nhiêu record, từ nguồn nào, có trùng không. Đây là requirement mà thầy nhấn mạnh trong buổi bảo vệ đề cương."

---

### Demo 6 – Time travel với Iceberg (1 phút, nếu thầy hỏi về Iceberg)

```powershell
cd backend
python -c "
from app.lakehouse.iceberg_manager import get_iceberg_manager
manager = get_iceberg_manager()
snapshots = manager.list_snapshots('bronze')
print('Tổng snapshot:', len(snapshots))
print('Current snapshot:', manager.get_current_snapshot('bronze'))
"
```

**Giải thích cho thầy:** "Iceberg lưu lại mỗi lần commit như một snapshot. Em có thể đọc dữ liệu như 3 ngày trước (`as_of_timestamp='3d'`), hoặc rollback về phiên bản cũ nếu phát hiện bug. Đây là điểm mạnh của Iceberg so với Parquet thường."

---

### Demo 7 – API Endpoint (2 phút)

**Bước 1:** Mở trình duyệt → <http://localhost:8000/docs>

**Bước 2:** Thử endpoint:
- `GET /api/v1/health` → click "Try it out" → Execute
- `POST /api/v1/pipeline/run` → body `{"symbol": "AAPL", "interval": "1d"}` → Execute
- `GET /api/v1/indicators/AAPL` → Execute

**Bước 3:** (nếu có React) Mở <http://localhost:5173> → Dashboard → xem chart VCB/FPT/HPG

**Giải thích cho thầy:** "Đây là FastAPI tự động sinh documentation từ code. Không cần Postman. Frontend React kết nối qua `/api/v1` proxy."

---

### Demo 8 – AI Agent (2 phút, nếu có GEMINI_API_KEY)

```powershell
cd backend
python -c "
from app.agent import Agent
a = Agent()
r = a.process('So sánh RSI của AAPL và MSFT ngày hôm nay')
print(r)
"
```

**Giải thích cho thầy:** "Agent nhận câu hỏi → gọi tool `calculate_indicators` → lấy kết quả Gold → trả lời. Không bịa giá, không hallucinate vì luôn truy vấn dữ liệu thật."

---

### Checklist trước khi demo

- [ ] `docker compose ps` — 4 service UP
- [ ] `python -c "from app.pipelines import run_symbol_pipeline"` — không lỗi
- [ ] Đã ingest ít nhất 1 mã (AAPL hoặc VCB)
- [ ] FastAPI đang chạy (`uvicorn app.main:app`)
- [ ] MinIO console accessible (<http://localhost:9001>)
- [ ] Nếu có key: `GEMINI_API_KEY` đã set trong `.env`

### 12.13. Demo tổng hợp – script in ra data thật (không fake)

Sau khi đã có data trong Bronze/Silver/Gold, dùng script tổng hợp này để in ra **toàn bộ data thật** cho thầy xem:

```powershell
cd backend
python scripts/demo_show_full.py
```

Script sẽ in 6 phần:

```
======================================================================
STOCK LAKEHOUSE - DEMO DATA (real market data, no synthetic)
======================================================================
[Storage] MinioStorageBackend (backend_name=minio)
[Buckets] stock-bronze, stock-silver, stock-gold (MinIO)

======================================================================
[1] DATA INVENTORY
======================================================================
  AAPL:
      BRONZE rows=  100 cols= 10 range=[2026-05-11 -> 2026-10-01] (143 days)
      SILVER rows=  100 cols= 12 range=[2026-05-11 -> 2026-10-01] (143 days)
      GOLD   rows=  100 cols= 94 range=[2026-05-11 -> 2026-10-01] (143 days)

  VCB:
      BRONZE rows= 2494 cols= 10 range=[2016-10-03 -> 2026-10-02] (3651 days)
      SILVER rows= 2486 cols= 12 range=[2016-10-03 -> 2026-10-02] (3651 days)
      GOLD   rows= 2486 cols= 94 range=[2016-10-03 -> 2026-10-02] (3651 days)

======================================================================
[2] BRONZE LAYER - raw data from external API (VCB first 20 rows)
======================================================================
symbol   timestamp            open    high     low   close    volume   source
  VCB 2016-10-03 00:00:00+00:00 15710.0 15830.0 15460.0 15550.0 1293590.0 ssi_vn
  VCB 2016-10-04 00:00:00+00:00 15550.0 15830.0 15500.0 15550.0 1653180.0 ssi_vn
  ...

======================================================================
[3] SILVER LAYER - cleaned data with stats
======================================================================
Last 10 rows của VCB (close 57.200 VND, volume 1.4M, ...)

======================================================================
[4] GOLD LAYER - features ready for ML/DL (VCB last 10 rows)
======================================================================
94 features gồm: sma_5/20/50, ema_12/26, rsi_14, macd, signal_line,
bb_upper/lower, return_1d, target_close_next, target_direction_next

======================================================================
[5] LINEAGE - which source was each symbol fetched?
======================================================================
  AAPL:
    provider: multi_source   records=100   partitions=6 (Hive-style)
  VCB:
    provider: ssi_vn         records=2494  partitions=121 (Hive-style)

======================================================================
[6] QUALITY REPORT - VCB quality stats
======================================================================
  record_count:        2486
  source_count:       2494
  invalid_ohlc_count: 8   (bị loại vì OHLC không hợp lệ)
  quality_status:     warning
```

**Câu nói với thầy:** *"Đây là 100% dữ liệu thật — em lấy từ SSI iBoard public API (cổ phiếu VN) và Alpha Vantage (cổ phiếu US). VCB có 2.486 phiên × 94 cột đặc trưng kỹ thuật trong 10 năm (2016–2026). Cột `invalid_ohlc_count=8` cho thấy Silver đã phát hiện và ghi riêng vào `_errors/` chứ không xóa âm thầm. Tất cả data trên đều nằm trong MinIO (object storage), truy vết được qua `_lineage.json`."*

### 12.14. Ingest thêm data VN từ SSI (nếu thầy muốn xem nhiều mã VN)

```powershell
cd backend
python scripts/demo_ingest_vcb.py     # ingest VCB từ SSI (2.500 năm nhật)
python scripts/demo_ingest.py          # ingest AAPL, MSFT, VCB (multi_source)
```

---

## 13. Các câu hỏi dự đoán và câu trả lời

### Q1: Tại sao cần 3 tầng, không gộp thành 1 tầng "data lake"?

> Vì mỗi tầng có **trách nhiệm khác nhau** và **người dùng khác nhau**:
> - Bronze giữ dữ liệu gốc → data engineer debug.
> - Silver là "single source of truth" sạch → analyst, modeler.
> - Gold là dataset ML-ready → data scientist.
>
> Nếu gộp, khi em đổi logic làm sạch → phải chạy lại từ nguồn → tốn request API, có thể bị rate limit. Bronze giữ nguyên → chỉ cần chạy lại Silver → Gold.

### Q2: Làm sao đảm bảo dữ liệu không bị mất khi deduplicate?

> Em **không xóa** bản ghi trùng. Quy trình:
> 1. Đọc partition hiện có.
> 2. `concat` với dữ liệu mới.
> 3. `drop_duplicates(keep="last")` — giữ bản mới hơn.
> 4. Số bản ghi trùng được **đếm và ghi vào `_lineage.json`**.
>
> Nếu cần khôi phục bản cũ → có `ingestion_time` trong mỗi record → có thể filter lại.

### Q3: Vì sao chọn Iceberg mà không phải Delta Lake?

> Hai lý do chính:
> 1. **Không lock-in**: Delta Lake gắn Databricks, Iceberg được hỗ trợ bởi nhiều engine (Spark, Flink, Trino, DuckDB, Snowflake, StarRocks). Em muốn demo hệ thống mở, không phụ thuộc 1 vendor.
> 2. **Partition evolution**: Iceberg cho phép đổi partition scheme mà không rewrite toàn bộ data. Delta Lake không có tính năng này.
>
> Tham khảo: spec Iceberg tại <https://iceberg.apache.org/spec/>, tháng 9/2026 đã lên bản 1.5.

### Q4: Look-ahead leakage xử lý thế nào?

> Em áp dụng 3 biện pháp:
> 1. **Chia train/test theo thời gian** (không dùng `train_test_split` ngẫu nhiên).
> 2. **Dùng `shift()` đúng chiều**: target `return_1d` tính từ close_t và close_{t-1}, không dùng close_{t+1}.
> 3. **Không fill NaN bằng 0**: vì 0 là giá trị có ý nghĩa trong trading.

### Q5: Tại sao chọn Pandas thay vì Spark cho Silver?

> - **Pandas**: xử lý 1 máy, in-process, code ngắn gọn, debug nhanh. Phù hợp với dataset hiện tại (~120.000 rows Gold, ~250.000 rows Silver).
> - **Spark**: phân tán trên nhiều executor, nhanh với data lớn (hàng triệu rows) nhưng cần Docker container riêng, JVM, khởi động cluster 15–30s, debug khó hơn.
>
> Em chọn Pandas vì (1) dataset hiện tại chưa đến ngưỡng cần Spark, (2) muốn giữ hạ tầng Docker tối giản (4 service thay vì 7), (3) đồ án solo, ngân sách operational có hạn. Logic validate OHLC/dedupe/timezone đều tách riêng nên sau này scale lên có thể chuyển sang Spark mà không phải đổi business rule.

### Q6: Nếu MinIO chết thì sao?

> Code tự động fallback về `LocalStorageBackend` (filesystem `backend/data/`) khi MinIO không khả dụng. Không crash, không mất dữ liệu. Khi MinIO khởi động lại, đổi biến môi trường `STORAGE_BACKEND=minio` → chuyển về MinIO. Không cần sửa code.

### Q7: Cổ phiếu Việt Nam (VCB, FPT, HPG) lấy từ đâu?

> Em dùng **SSI iBoard public API** qua `SSIVNProvider`. Đây là API công khai của SSI (công ty chứng khoán lớn tại Việt Nam), cung cấp dữ liệu HOSE, HNX, UPCOM miễn phí. Nếu SSI API lỗi → fallback sang web scraper CafeF. Đã verify 50/53 symbols có dữ liệu 5-10 năm (xem [`docs/vn_data_quality.md`](vn_data_quality.md)).

### Q8: Tại sao không dùng Airflow lập lịch?

> Em ưu tiên **đúng → nhanh** hơn **hoàn thiện → chậm**. Airflow là orchestration layer phức tạp, đặt lên trên khi data pipeline đã ổn định production. Hiện tại em dùng **cron-like scheduler** qua `scripts/schedule_batch.py` (chạy ingest + pipeline hàng ngày), đủ cho prototype. Airflow cần thêm ít nhất 2 service nữa (Redis + Airflow webserver/worker), tăng độ phức tạp vận hành không cần thiết cho đồ án.

### Q9: Dữ liệu có đủ để train model không?

> Với 1 mã cổ phiếu 10 năm daily → ~2.500 rows. Đủ cho proof-of-concept với LSTM (sequence length 60, train ~2.400 rows). Khi mở rộng nhiều mã (50-100 symbols) hoặc dùng intraday (1h, 15m) → số lượng rows tăng gấp nhiều lần. Đã verify 3 model (Linear Regression, ARIMA, LSTM) chạy được trên `forecast/compare/{symbol}` endpoint, trả MAE/RMSE/MAPE/Directional Accuracy.

### Q10: Kafka dùng để làm gì?

> Kafka trong kiến trúc hiện tại dùng cho **real-time streaming**. Pipeline đầy đủ: `Finnhub WebSocket (Free tier) → StreamPublisher gom 1s OHLCV → Kafka topic stock-ohlcv-raw → Kafka Consumer → Bronze/Silver/Gold`. Em đã có đầy đủ code (`app/streaming/finnhub_websocket.py`, `stream_publisher.py`, `kafka_producer.py`, `kafka_consumer.py`) và CLI scripts (`run_stream_publisher.py`, `run_stream_consumer.py`). Hiện tại ưu tiên demo batch data trước, streaming sẽ bật khi demo live update.

### Q11: AI Agent dùng LLM nào, có cần API key trả phí không?

> Agent dùng **Gemini Free API** (`gemini-2.0-flash-exp`) qua Google AI Studio. Free tier 60 req/min, không cần thẻ tín dụng. Đặt `GEMINI_API_KEY` trong `.env` là chạy được. Nếu không có key, agent tự động fallback về **local tool router** - vẫn gọi đúng backend tools (14+ tools: market_summary, query_stock_data, calculate_indicators, run_backtest, ...), chỉ khác là câu trả lời được compose từ kết quả tool thay vì LLM sinh tự do. Lịch sử chat lưu vào bảng `agent_conversations` (MySQL).

### Q12: Frontend kết nối Backend bằng gì, có vấn đề CORS không?

> Frontend (Vite) chạy ở `http://127.0.0.1:5173`, Backend (FastAPI) ở `http://127.0.0.1:8000`. CORS đã whitelist sẵn (`CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173` trong `.env`). Đồng thời Vite proxy `/api/v1` → `http://127.0.0.1:8000` nên khi dev có thể gọi `/api/v1/...` trực tiếp từ browser, không cần CORS. Build production (`npm run build`) tạo static, deploy bất kỳ web server nào (nginx, caddy, ...).

---

> **Tự đánh giá (cập nhật 01/10/2026):**
>
> | Tiêu chí | Đánh giá |
> |----------|----------|
> | Kiến trúc tổng thể | Rõ ràng, đúng Medallion, có sơ đồ luồng minh họa |
> | Tính đúng đắn dữ liệu | Validate schema, OHLC rule, dedup, ghi `_quality.json` |
> | Khả năng truy vết | Lineage + quality metadata đầy đủ |
> | Chống leakage | Chia time-series, dùng `shift()` đúng chiều |
> | Mức độ hoàn thành | ~95% tổng thể (Bronze/Silver/Gold + ML + Backtest + Agent + Frontend đều chạy end-to-end) |
> | Rủi ro đã kiểm soát | Data quality, failover, multi-provider, local LLM fallback, synthetic fallback cho UI demo |
>
> **Tình trạng chung:** Đúng hướng, nền tảng dữ liệu đã vững. Trọng tâm tuần 3–4: hoàn thiện Gold + baseline + LSTM + API.

---

## 14. Cheat Sheet – Syntax Python quan trọng xuất hiện trong code

### 14.1. Pandas

| Syntax | Ý nghĩa | Ví dụ |
|--------|----------|--------|
| `df[col].isna().any(axis=1)` | True ở dòng có ít nhất 1 NaN | dùng làm mask lọc lỗi |
| `df.drop_duplicates(subset=[...], keep="last")` | Bỏ trùng, giữ bản mới nhất | dedupe |
| `series.rolling(window=20).mean()` | Moving average 20 ngày | SMA |
| `series.ewm(span=12).mean()` | Exponential weighted MA | EMA, RSI |
| `series.pct_change()` | `(close_t - close_{t-1}) / close_{t-1}` | return 1 ngày |
| `series.shift(1)` | Lấy giá trị 1 dòng TRƯỚC | lag feature |
| `series.shift(-1)` | Lấy giá trị 1 dòng SAU | target (future) |
| `df.concat([a, b], axis=1)` | Ghép theo **cột** | thêm indicator columns |
| `df.drop(columns=[...])` | Xóa cột | idempotent feature strip |
| `df.loc[mask, col] = val` | Gán theo mask boolean | ghi error_reason |

### 14.2. Type hints (PEP 484 / Python 3.10+)

| Syntax | Ý nghĩa |
|--------|----------|
| `str \| None` | Union — nhận str hoặc None (Python 3.10+) |
| `dict[str, list[str]]` | Dict với key str, value list[str] |
| `tuple[int, ...]` | Tuple bất biến |
| `list[pd.DataFrame]` | List chứa DataFrame |
| `@dataclass` | Auto-generate `__init__`, `__repr__` |

### 14.3. Decorator

| Syntax | Ý nghĩa |
|--------|----------|
| `@abstractmethod` | Bắt buộc override trong class con |
| `@dataclass` | Auto-generate constructor + repr |
| `@property` | Getter — gọi như attribute (`obj.name` thay vì `obj.name()`) |
| `@staticmethod` | Không cần `self`, gọi `Class.method()` |

### 14.4. Exception handling

```python
# raise kèm chain
raise DataSourceError("msg") from exc

# nuốt lỗi nhưng log
try:
    ...
except Exception as e:
    logger.warning("msg: %s", e)
    pass

# guard chống ZeroDivisionError
max(1, denominator)
```

### 14.5. Dataclass + field

```python
@dataclass
class PipelineRun:
    run_id: str
    status: str = "running"
    errors: list[str] = field(default_factory=list)  # ⚠ KHÔNG dùng =[] vì share
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### 14.6. DuckDB / PyArrow Parquet

| Syntax | Ý nghĩa |
|--------|----------|
| `df.to_parquet(path, engine="pyarrow", index=False)` | Ghi Parquet |
| `pd.read_parquet(path, engine="pyarrow")` | Đọc Parquet |
| `frame.to_parquet(BytesIO(), engine="pyarrow")` | Serialize → bytes (dùng cho MinIO) |
| `pd.read_parquet(BytesIO(bytes), engine="pyarrow")` | Deserialize bytes → DataFrame |

### 14.7. Environment / Config

```python
# settings là singleton đọc .env 1 lần
from app.core.config import settings
settings.storage_backend      # → "minio" hoặc "local"
settings.finnhub_api_key    # → "datkbq9r01..."

# lru_cache — đọc .env 1 lần, cache vĩnh viễn
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## 15. Glossary – Thuật ngữ

| Thuật ngữ | Giải thích |
|-----------|------------|
| **Bronze / Silver / Gold** | Ba vùng trong Medallion Architecture. Bronze = raw, Silver = clean, Gold = ML-ready |
| **OHLCV** | Open, High, Low, Close, Volume — 5 cột cơ bản của 1 bar |
| **Adj Close** | Adjusted Close — giá đã điều chỉnh split/cổ tức |
| **Dedup** | Deduplication — bỏ dòng trùng |
| **Mask (boolean)** | Series True/False dùng để filter dòng |
| **Partition (Hive-style)** | Cách tổ chức file: `symbol=AAPL/year=2026/month=09/` |
| **Parquet** | Định dạng columnar storage, nén tốt, đọc nhanh |
| **Lineage** | Metadata ghi "bản ghi này lấy từ đâu, lúc nào" |
| **Quality report** | JSON ghi số lỗi, quality status |
| **Look-ahead leakage** | Bug khi dùng future data trong training — model "nhìn thấy đáp án" |
| **Shift(-1)** | Lấy giá trị 1 bước TƯƠNG LAI (dùng cho target, không phải feature) |
| **Rolling window** | Cửa sổ trượt — tính MA, RSI trên N ngày gần nhất |
| **EMA vs SMA** | SMA = trung bình cộng đơn giản. EMA = trung bình có trọng số exponential |
| **RSI** | Relative Strength Index — momentum oscillator [0, 100] |
| **MACD** | Moving Average Convergence Divergence — trend momentum |
| **Bollinger Bands** | Dải ±2σ quanh SMA — đo volatility |
| **Idempotent** | Chạy bao nhiêu lần cũng cho kết quả giống nhau |
| **Factory pattern** | Design pattern: 1 hàm/class chọn implementation theo config |
| **Adapter pattern** | Wrapper quanh external API để统一 interface |
| **MultiSourceProvider** | Failover chain — thử nhiều provider cho đến khi có data |
| **MinIO** | S3-compatible object storage chạy local |
| **Apache Iceberg** | Table format với time travel, schema evolution |
| **PyArrow** | Thư viện đọc/ghi Parquet (backend cho Pandas) |
| **Dataclass** | Class với auto-constructor từ type hints |
| **`__future__ import annotations`** | Cho phép dùng `list[str]`, `dict[str, ...]` thay vì `List[str]` từ typing |
| **PyIceberg** | Thư viện Python để đọc/ghi Iceberg tables |
| **SQLAlchemy** | ORM — ánh xạ bảng MySQL thành class Python |
| **FastAPI Pydantic** | Validate request/response JSON |
| **`f"string {var}"`** | f-string — nhúng biến vào string |
| **`dict.keys() / dict.items() / dict.values()`** | View objects — iterable trên dict |
| **`sorted(list, reverse=True)`** | Sắp xếp, trả list mới |
| **`isinstance(obj, type)`** | Kiểm tra kiểu runtime |
| **`hasattr(obj, name)`** | Kiểm tra object có attribute không |
| **`getattr(obj, name, default)`** | Lấy attribute với default |
| **`setdefault(key, default)`** | Nếu key chưa có → set rồi trả về |
| **`Counter.most_common(n)`** | Trả n phần tử hay xuất hiện nhất |
| **`dataclasses.field(default_factory=list)`** | Tạo list mới mỗi instance, không share giữa các instance |
| **`from __future__ import annotations`** | Trì hoãn evaluate type hints — cho phép forward reference và syntax mới |
| **Docker volume named** | `volumes: - mysql_data:/var/lib/mysql` — persist data kể cả khi container restart |

---

## 16. Nguồn tham khảo nhanh

| Topic | Link |
|-------|------|
| Pandas docs | https://pandas.pydata.org/docs/ |
| PyArrow Parquet | https://arrow.apache.org/docs/python/parquet.html |
| Apache Iceberg spec | https://iceberg.apache.org/spec/ |
| PyIceberg docs | https://py.iceberg.apache.org/ |
| MinIO Python SDK | https://min.io/docs/mino/linux/integrations/python-sdk.html |
| yfinance | https://github.com/ranaroussi/yfinance |
| Medallion Architecture | https://www.databricks.com/glossary/medallion-architecture |
| RSI formula | https://www.investopedia.com/terms/r/rsi.asp |
| MACD formula | https://www.investopedia.com/terms/m/macd.asp |
| Bollinger Bands | https://www.investopedia.com/terms/b/bollingerbands.asp |
| Docker Compose | https://docs.docker.com/compose/ |
| Python dataclasses | https://docs.python.org/3/library/dataclasses.html |
| Type hints cheatsheet | https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html |

---
