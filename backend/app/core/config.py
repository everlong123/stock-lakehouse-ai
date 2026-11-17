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
    minio_bucket_silver_fundamentals: str = "stock-silver-fundamentals"

    use_spark: bool = False
    spark_app_name: str = "stock-lakehouse"
    spark_master: str = "local[*]"

    # Gemini Free API (Google AI Studio - free tier)
    gemini_api_key: str = ""
    # Default model. The old "gemini-2.0-flash-exp" alias now returns HTTP 404
    # ("no longer available"), and the "gemini-flash-latest" alias HANGS for
    # 75s+ on this project key before the socket times out - both were making
    # the agent look like it was "thinking" for minutes before falling back.
    # "gemini-3.5-flash-lite" answers in ~1.5s and stays inside the free tier.
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    # Per-HTTP-attempt timeout. Kept short on purpose: a hung model must fail
    # fast so the fallback chain can move on instead of burning the request.
    gemini_timeout_seconds: int = 25

    # ── Background work (off for a "minimal" / demo run) ───────────────────
    # Each of these spawns a background thread that keeps the box busy even
    # when nobody is looking at the UI. Turn them off to run the API in a
    # low-footprint mode; the REST endpoints still work, they just don't
    # proactively fetch or re-count anything.
    #
    #   warm_layer_counts_on_start -> pre-counts Bronze/Silver/Gold objects at
    #     startup. This walks ~300k objects in MinIO, so it costs 20-30s of
    #     CPU on boot for a page the user may never open.
    warm_layer_counts_on_start: bool = True
    #   crawl_enabled -> continuous background fetch every crawl_interval_seconds.
    #   auto_refresh_enabled -> incremental Bronze->Silver->Gold refresh pass
    #     (958 symbols by default) on startup, then every 6h.
    auto_refresh_enabled: bool = True

    # Automatic next-session forecasting.
    #
    # When this is on, the refresh pass calls `predict_symbol()` for every
    # symbol that has a trained model, right after its Silver/Gold layers
    # are rebuilt, and stores the result in the `predictions` table.
    #
    # WHY IT IS OFF BY DEFAULT
    # ------------------------
    # The `predictions` table needs its Alembic migration (0002). With the
    # flag on and the migration missing, the write fails - and a failed write
    # must never take the refresh pass down with it. The code catches that
    # and skips the symbol, but then the flag would be lying about what the
    # system does, so it defaults to off until the migration is applied.
    #
    # NOTE: this NEVER trains a model. It only uses models that already
    # exist on disk. Training happens manually, on a machine with enough
    # RAM for the LSTM.
    auto_predict_enabled: bool = False
    # The model used for the automatic next-session forecast. It must be a
    # model that has already been trained for the symbol.
    #
    # WHY LINEAR REGRESSION AND NOT ARIMA
    # -----------------------------------
    # Measured on the lakehouse (13/11/2026): 973 symbols have a trained
    # `linear_regression` model, 8 have `arima`, 6 have `lstm`. Pointing
    # this at `arima` would silently skip ~965 symbols - the forecast would
    # "succeed" for a handful of tickers and produce nothing for the rest
    # of the universe, without any error.
    #
    # Linear regression is also the model the scheduled universe job uses
    # (`run_scheduled_job.py universe-forecast --model linear_regression`),
    # so both paths agree on the number.
    auto_predict_model: str = "linear_regression"

    # LLM provider selection: "gemini" (recommended - free tier) or "local"
    # (offline tool router fallback when no API key is configured).
    llm_provider: Literal["gemini", "local"] = "gemini"

    # Server-side deadline for one agent chat request.
    #
    # WHY: the frontend aborts an axios request after 90s and shows
    # "Yêu cầu mất quá lâu". When the server keeps working after that abort,
    # the user sees a timeout even though the answer was about to arrive, and
    # the orphaned work keeps competing for CPU and MinIO connections with
    # the next request.
    #
    # The deadline is deliberately shorter than the frontend's 90s so the
    # server can return a real, actionable error (a 504 with an explanation)
    # instead of letting the client time out blind. Raise it only if the
    # tool set gets genuinely slower; the auto-refresh contention that used
    # to dominate these requests has been fixed, so the heavy tools now
    # finish in seconds rather than minutes.
    agent_request_timeout_seconds: int = 75

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
        "yahoo_http",
        "stooq",
        "multi_source",
    ] = "yfinance"
    yfinance_timeout: int = 30
    alpha_vantage_api_key: str = ""
    finnhub_api_key: str = ""
    finnhub_webhook_secret: str = ""

    # Crawler settings
    crawl_enabled: bool = True
    crawl_interval_seconds: int = 300  # 5 minutes
    # US stocks: top 5 liquid tickers — enough for the demo, easy to reason about.
    crawl_symbols: str = "AAPL,MSFT,NVDA,TSLA,GOOGL"

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
