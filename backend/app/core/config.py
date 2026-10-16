"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent

# .env.local (machine-specific overrides, not committed) is loaded into
# os.environ BEFORE pydantic-settings reads the canonical .env, so values
# in .env.local win. Production deployments should not have .env.local.
_LOCAL_ENV = BACKEND_ROOT / ".env.local"
if _LOCAL_ENV.exists():
    for _line in _LOCAL_ENV.read_text(encoding="utf-8").splitlines():
        # Strip leading whitespace and inline comments before "=" parse
        _stripped = _line.strip()
        if not _stripped or _stripped.startswith("#") or "=" not in _stripped:
            continue
        _k, _, _v = _stripped.partition("=")
        _k = _k.strip()
        _v = _v.strip()
        # Remove inline # comments from value (only outside quotes - good enough
        # for our flat .env.local format).
        if "#" in _v and not (_v.startswith('"') or _v.startswith("'")):
            _v = _v.split("#", 1)[0].strip()
        _v = _v.strip('"').strip("'")
        # Only set if not already in real env (so exports in shell still win).
        if _k and _k not in os.environ:
            os.environ[_k] = _v
    _line = _stripped = _k = _v = None


class Settings(BaseSettings):
    """Runtime configuration for the Stock Lakehouse platform."""

    model_config = SettingsConfigDict(
        # .env values are loaded after we already injected .env.local into
        # os.environ above, so .env.local wins for any key it defines.
        env_file=(str(BACKEND_ROOT / ".env"), str(PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )

    app_name: str = "Stock Lakehouse AI"
    app_env: Literal["development", "production", "test"] = "development"
    app_debug: bool = True

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175,https://*.vercel.app"

    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "stock_lakehouse"
    mysql_user: str = "root"
    mysql_password: str = "123456"
    database_url: str = "mysql+pymysql://root:123456@localhost:3306/stock_lakehouse"

    storage_backend: Literal["local", "minio"] = "local"
    data_root: str = "data"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_bronze: str = "stock-bronze"
    minio_bucket_silver: str = "stock-silver"
    minio_bucket_gold: str = "stock-gold"
    minio_bucket_models: str = "stock-models"
    minio_bucket_backtests: str = "stock-backtests"
    minio_bucket_silver_news: str = "stock-silver-news"
    minio_bucket_silver_fundamentals: str = "stock-silver-fundamentals"
    minio_bucket_gold_features: str = "stock-gold-features"

    use_spark: bool = False
    spark_app_name: str = "stock-lakehouse"
    spark_master: str = "local[*]"

    # Gemini Free API (Google AI Studio - free tier)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-exp"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: int = 60

    # LLM provider selection: "gemini" (recommended - free tier) or "local"
    # (offline tool router fallback when no API key is configured).
    llm_provider: Literal["gemini", "local"] = "gemini"

    default_symbol: str = "AAPL"
    default_interval: str = "1d"
    default_lookback_days: int = 3650  # ~10 years (exceeds 5-year requirement)

    # Single-interval lakehouse - only daily bars are collected.
    # Intraday (1h/15m/5m) collection is intentionally disabled so the
    # Bronze/Silver/Gold tables stay 1d-aligned and easy to reason about.

    model_dir: str = "data/models"
    random_seed: int = 42

    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15

    lstm_sequence_length: int = 60
    lstm_hidden_size: int = 64
    lstm_num_layers: int = 2
    lstm_dropout: float = 0.2
    lstm_learning_rate: float = 0.001
    lstm_batch_size: int = 32
    lstm_epochs: int = 20
    lstm_patience: int = 5

    arima_order: str = "5,1,0"

    data_source: Literal[
        "yfinance",
        "yfinance_direct",
        "alpha_vantage",
        "finnhub",
        "web_scraper",
        "vnstock",
        "ssi_vn",
        "vn_ws",
        "vn_ws_rest",
        "yahoo_http",
        "stooq",
        "multi_source",
    ] = "yfinance"
    yfinance_timeout: int = 30
    alpha_vantage_api_key: str = ""
    finnhub_api_key: str = ""
    finnhub_webhook_secret: str = ""

    # ── Finnhub WebSocket (Free tier caps at 50 symbols / ~50 msgs/sec) ───────
    finnhub_ws_symbols: str = "AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META,AMD"
    finnhub_ws_ping_interval: int = 25
    finnhub_ws_max_reconnect: int = 10

    # ── SSI iBoard WebSocket (Vietnam - FREE, no API key, public endpoint) ──
    # Endpoint: wss://iboard-pushstream.ssi.com.vn/realtime (used by iboard.ssi.com.vn)
    # Boards: MAIN = HOSE, HNX = Hanoi, UPCOM = UPCoM
    vn_ws_symbols: str = "FPT,VNM,VCB,HPG,MWG,VIC,VHM,MSN,BID,CTG"
    vn_ws_boards: str = "MAIN,HNX,UPCOM"
    vn_ws_dead_man_seconds: int = 60
    vn_ws_max_reconnect: int = 10
    vn_ws_enabled: bool = True

    # Crawler settings
    crawl_enabled: bool = True
    crawl_interval_seconds: int = 300  # 5 minutes
    # US stocks: top 5 liquid tickers — enough for the demo, easy to reason about.
    crawl_symbols: str = "AAPL,MSFT,NVDA,TSLA,GOOGL"

    # ── US EOD poller (yfinance 1d bars, free) ─────────────────────────────
    # Replaces the deprecated Finnhub REST candle endpoint (free tier no
    # longer has access since 2025-04). Off by default — flip the env on if
    # you want 1d bars published into the Kafka raw topic between batches.
    us_eod_poller_enabled: bool = False
    us_eod_poller_interval_seconds: int = 300  # 5 minutes
    # Top 20 US blue-chips — keeps the lakehouse populated without tripping
    # the unofficial yfinance rate limit (~2k req/hour from a single IP).
    us_eod_poller_symbols: str = (
        "AAPL,MSFT,NVDA,TSLA,GOOGL,AMZN,META,AMD,NFLX,INTC,"
        "JPM,V,BAC,WMT,JNJ,UNH,XOM,KO,DIS,ORCL"
    )
    # Resolved on first tick so ``rest_poller`` is a backward-compat shim.
    us_rest_poller_enabled: bool = False

    # ── VN REST poller (SSI iBoard, public REST, no API key) ──────────────
    # Vietnamese tickers (HOSE/HNX/UPCoM) are not on yfinance, so they need
    # their own poll path. Pulls from the same SSI iBoard public REST endpoint
    # the WebSocket path uses, at 1-minute cadence. Off by default.
    vn_rest_poller_enabled: bool = False
    vn_rest_poller_interval_seconds: int = 60

    # ── Apache Iceberg ────────────────────────────────────────────────────────
    use_iceberg: bool = False  # Set True to use Iceberg instead of raw Parquet
    iceberg_catalog_uri: str = "http://localhost:8181"
    iceberg_warehouse: str = "s3://stock-lakehouse/iceberg"

    # ── Apache Kafka (Real-time Streaming) ────────────────────────────────────
    use_kafka: bool = False  # Set True to enable Kafka streaming
    kafka_bootstrap_servers: str = "localhost:9094"
    kafka_topic_raw: str = "stock-ohlcv-raw"
    kafka_consumer_group: str = "stock-lakehouse-consumer"

    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    @field_validator("train_ratio", "validation_ratio", "test_ratio")
    @classmethod
    def validate_ratio(cls, value: float) -> float:
        if value <= 0 or value >= 1:
            raise ValueError("Split ratios must be between 0 and 1.")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def backend_root(self) -> Path:
        return BACKEND_ROOT

    @property
    def data_root_path(self) -> Path:
        path = Path(self.data_root)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path

    @property
    def model_dir_path(self) -> Path:
        path = Path(self.model_dir)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path

    @property
    def log_file_path(self) -> Path:
        path = Path(self.log_file)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path

    @property
    def arima_order_tuple(self) -> tuple[int, int, int]:
        parts = [int(item.strip()) for item in self.arima_order.split(",")]
        if len(parts) != 3:
            raise ValueError("ARIMA_ORDER must be three integers, e.g. 5,1,0")
        return parts[0], parts[1], parts[2]

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
