"""System / project metadata tools for the AI agent.

These tools let the LLM look up real, live numbers about the platform itself
(how many symbols are tracked, which models have been trained, how big the
MinIO buckets are). The hardcoded :data:`PROJECT_CONTEXT` in
:mod:`app.agent.prompts` covers the "what is this project" questions; these
tools answer the "right now" questions that change as the lakehouse grows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.constants import (
    CRYPTO_SYMBOLS,
    GLOBAL_SYMBOLS,
    MARKET_INDEXES,
    SUPPORTED_SYMBOLS,
    US_SYMBOLS,
    VN_SYMBOLS,
)
from app.core.logging_config import get_logger
from app.database.session import check_database_connection
from app.forecasting.model_registry import list_trained_models
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer
from app.lakehouse.storage_factory import get_storage_backend

logger = get_logger(__name__)


# ── pydantic schemas (no parameters for system queries; kept for parity) ──


class SymbolsInfoInput(BaseModel):
    region: str = Field(
        default="all",
        description="Lọc theo khu vực: 'all' (tất cả), 'us' (Mỹ), 'global' (toàn cầu), "
        "'vn' (Việt Nam qua SSI), 'crypto', 'index'.",
    )


class TrainedModelsInput(BaseModel):
    symbol: str | None = Field(
        default=None,
        description="Lọc theo mã cụ thể (bỏ trống = tất cả mã đã train).",
    )


class SystemArchitectureInput(BaseModel):
    detail_level: str = Field(
        default="summary",
        description="'summary' = mô tả ngắn gọn; 'full' = kèm chi tiết providers & tools.",
    )


class StorageStatsInput(BaseModel):
    layer: str = Field(
        default="all",
        description="Lớp lakehouse: 'all' (tổng), 'bronze', 'silver', 'gold', 'models', 'news', 'fundamentals'.",
    )


# ── helpers ────────────────────────────────────────────────────────────────


def _safe_count(layer: str) -> int:
    """Count objects in a MinIO/local bucket, never raising to the caller."""
    try:
        return int(get_storage_backend().count_objects(layer, ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("count_objects(%s) failed: %s", layer, exc)
        return -1


def _models_root() -> Path | None:
    """Return the on-disk model directory if it exists."""
    try:
        path = settings.model_dir_path
        return path if path.exists() else None
    except Exception:
        return None


def _discover_trained_symbols() -> list[str]:
    """List symbols that have at least one model trained on disk."""
    root = _models_root()
    if root is None:
        return []
    syms: list[str] = []
    try:
        for child in root.iterdir():
            if child.is_dir() and (child / "registry.json").exists():
                syms.append(child.name.upper())
            elif child.is_dir():
                # Some symbols may have a sub-model dir but the registry.json
                # lives a level deeper; treat them as trained if *any* model
                # subdir has registry.json.
                for sub in child.iterdir():
                    if sub.is_dir() and (sub / "registry.json").exists():
                        syms.append(child.name.upper())
                        break
    except Exception as exc:  # noqa: BLE001
        logger.warning("discover trained symbols failed: %s", exc)
    return sorted(set(syms))


def _summarise_trained_models(symbol: str) -> list[dict[str, Any]]:
    """Return a slim summary for each trained model of a symbol."""
    records = list_trained_models(symbol)
    out: list[dict[str, Any]] = []
    for rec in records:
        out.append(
            {
                "model_name": rec.get("model_name"),
                "symbol": rec.get("symbol", symbol.upper()),
                "mae": rec.get("mae"),
                "rmse": rec.get("rmse"),
                "mape": rec.get("mape"),
                "directional_accuracy": rec.get("directional_accuracy"),
            }
        )
    return out


# ── public tools ──────────────────────────────────────────────────────────


def get_symbols_info(region: str = "all") -> dict[str, Any]:
    """Trả về thống kê về các mã chứng khoán mà hệ thống hỗ trợ.

    Phân loại theo khu vực (US / toàn cầu / crypto / chỉ số). Khi được hỏi
    kiểu "có bao nhiêu mã?" hoặc "hệ thống theo dõi những mã nào?", agent
    sẽ gọi tool này thay vì bịa số.
    """
    region = (region or "all").lower().strip()

    all_count = len(GLOBAL_SYMBOLS) + len(MARKET_INDEXES) + len(CRYPTO_SYMBOLS) + len(VN_SYMBOLS)

    payload: dict[str, Any] = {
        "total_symbols": all_count,
        "regions": {
            "us": len(US_SYMBOLS),
            "global": len(GLOBAL_SYMBOLS),
            "vn": len(VN_SYMBOLS),
            "vn_top10_streamed": [
                s.strip() for s in settings.vn_ws_symbols.split(",") if s.strip()
            ],
            "market_indexes": len(MARKET_INDEXES),
            "crypto": len(CRYPTO_SYMBOLS),
        },
        "supported_symbols_count": len(SUPPORTED_SYMBOLS),
        "vn_realtime_enabled": settings.vn_ws_enabled,
        "data_sources": [
            "yfinance (Python package, key-less, 10y+ history)",
            "yahoo_http (direct v8 chart API, browser UA)",
            "alpha_vantage (API key, free tier)",
            "finnhub (API key, free tier, real-time WebSocket)",
            "ssi_vn (SSI iBoard public, HOSE/HNX/UPCoM)",
        ],
        "notes": (
            "US_SYMBOLS là tập curated gồm các blue-chip/mid-cap có thanh khoản tốt. "
            "GLOBAL_SYMBOLS = US_SYMBOLS + EU/JP/HK/CN/IN/BR/CA/AU/KR/TW + ETFs. "
            "Mã Việt Nam chưa có trong GLOBAL_SYMBOLS vì yfinance không cover HOSE/HNX/UPCoM "
            "— chúng đi qua provider ssi_vn và top-10 được stream realtime qua WebSocket."
        ),
    }

    if region == "us":
        payload["sample_us_symbols"] = US_SYMBOLS[:25]
        payload["us_symbols_total"] = len(US_SYMBOLS)
    elif region == "global":
        payload["global_symbols_total"] = len(GLOBAL_SYMBOLS)
    elif region == "vn":
        payload["vn_top10_streamed"] = [
            s.strip() for s in settings.vn_ws_symbols.split(",") if s.strip()
        ]
        payload["vn_provider"] = "ssi_vn (SSI iBoard public REST)"
    elif region == "crypto":
        payload["crypto_symbols"] = CRYPTO_SYMBOLS
    elif region == "index":
        payload["market_indexes"] = MARKET_INDEXES

    return payload


def get_trained_models(symbol: str | None = None) -> dict[str, Any]:
    """Liệt kê các mô hình đã train (LR / ARIMA / LSTM / XGBoost) trong hệ thống.

    Trả về cả metrics (MAE/RMSE/MAPE/DA) cho mỗi model đã lưu. Khi user hỏi
    "mô hình nào đã train cho VCB?" hoặc "đã có bao nhiêu model?", agent
    sẽ gọi tool này.
    """
    out: dict[str, Any] = {
        "filter_symbol": symbol.upper() if symbol else None,
        "models": [],
        "summary": {
            "total_models": 0,
            "models_by_model_name": {},
            "symbols_with_at_least_one_model": 0,
        },
    }

    try:
        if symbol:
            models = _summarise_trained_models(symbol)
            out["models"] = models
            out["summary"]["total_models"] = len(models)
            out["summary"]["models_by_model_name"] = {
                m["model_name"]: 1 for m in models if m.get("model_name")
            }
            out["summary"]["symbols_with_at_least_one_model"] = (
                1 if models else 0
            )
        else:
            trained_symbols = _discover_trained_symbols()
            total = 0
            by_name: dict[str, int] = {}
            all_records: list[dict[str, Any]] = []
            for sym in trained_symbols:
                recs = _summarise_trained_models(sym)
                total += len(recs)
                for rec in recs:
                    name = rec.get("model_name") or "unknown"
                    by_name[name] = by_name.get(name, 0) + 1
                    all_records.append(rec)
            out["models"] = all_records[:50]  # cap so the JSON isn't massive
            out["models_truncated"] = len(all_records) > 50
            out["summary"] = {
                "total_models": total,
                "models_by_model_name": by_name,
                "symbols_with_at_least_one_model": len(trained_symbols),
                "trained_symbols_sample": trained_symbols[:20],
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_trained_models failed: %s", exc)
        out["error"] = str(exc)

    out["model_architecture_supported"] = [
        "linear_regression",
        "arima",
        "lstm",
        "xgboost",
    ]
    return out


def get_system_architecture(detail_level: str = "summary") -> dict[str, Any]:
    """Mô tả kiến trúc hệ thống (Bronze → Silver → Gold, providers, tech stack).

    Dùng kèm PROJECT_CONTEXT trong system prompt: prompt mang thông tin tóm
    tắt, tool này mang thông tin runtime (storage backend đang dùng là gì,
    có Kafka không, có Iceberg không...).
    """
    storage = get_storage_backend()
    detail_level = (detail_level or "summary").lower().strip()

    payload: dict[str, Any] = {
        "project_name": settings.app_name,
        "purpose": (
            "Nền tảng Data Lakehouse phân tích & dự báo chứng khoán phục vụ "
            "nghiên cứu học thuật. KHÔNG phải tư vấn đầu tư."
        ),
        "layers": {
            "bronze": {
                "description": "Dữ liệu OHLCV thô, append-only, partitioned theo symbol/year/month.",
                "format": "Parquet (columnar, compressed).",
                "schema": [
                    "symbol", "timestamp", "open", "high", "low", "close",
                    "adj_close", "volume", "source", "ingestion_time",
                ],
            },
            "silver": {
                "description": "Dữ liệu đã làm sạch: chuẩn hoá timezone, loại bỏ OHLC không hợp lệ, dedup.",
                "extras": ["news_silver", "fundamentals_silver"],
            },
            "gold": {
                "description": "Features + targets phục vụ ML (không look-ahead leakage).",
                "feature_columns_count": 23,
                "targets": ["target_close_next", "target_return_next", "target_direction_next"],
            },
        },
        "data_providers": [
            "yfinance (Python package, mặc định)",
            "yahoo_http (direct v8 chart API)",
            "alpha_vantage (cần API key)",
            "finnhub (cần API key, có WebSocket realtime)",
            "ssi_vn (SSI iBoard public, HOSE/HNX/UPCoM)",
            "stooq",
            "web_scraper",
            "multi_source (failover chain)",
        ],
        "models": ["linear_regression", "arima", "lstm", "xgboost"],
        "backtesting": {
            "strategies": ["ma_crossover", "rsi_strategy"],
            "validation": "walk-forward (train_period_days, test_period_days)",
        },
        "auto_refresh": {
            "on_startup": True,
            "interval_seconds": 6 * 3600,
            "scope": "Bronze → Silver → Gold cho tất cả symbols.",
        },
        "tech_stack": {
            "backend": "FastAPI (Python 3.11+)",
            "storage": "MinIO (S3-compatible) — fallback local filesystem khi MinIO down.",
            "metadata_db": "MySQL (Alembic migrations, pymysql driver).",
            "streaming": "Apache Kafka (opt-in, USE_KAFKA=true).",
            "table_format": "Apache Iceberg REST catalog (opt-in, USE_ICEBERG=true).",
            "compute": "Pandas (mặc định), PySpark (opt-in, USE_SPARK=true).",
            "frontend": "React + Vite (FE tách biệt, giao tiếp qua REST).",
        },
        "runtime": {
            "storage_backend": storage.backend_name,
            "data_source": settings.data_source,
            "use_spark": settings.use_spark,
            "use_kafka": settings.use_kafka,
            "use_iceberg": settings.use_iceberg,
            "llm_provider": settings.llm_provider,
        },
        "agent_tools_count": 16,
        "agent_tools": [
            "query_stock_data", "get_market_summary",
            "calculate_indicators",
            "forecast_stock", "compare_models",
            "run_backtest", "run_walk_forward",
            "get_news_for_symbol", "get_sentiment_summary",
            "get_sentiment_timeseries", "get_market_news",
            "get_fundamental_metrics", "get_income_statement",
            "get_balance_sheet", "get_cash_flow",
            "get_market_index", "get_orderbook",
        ],
        "disclaimer": (
            "Đây là prototype nghiên cứu học thuật. Kết quả KHÔNG phải khuyến nghị "
            "đầu tư và KHÔNG cam kết lợi nhuận tương lai."
        ),
    }

    if detail_level == "full":
        payload["env_keys_relevant"] = [
            "DATA_SOURCE", "STORAGE_BACKEND", "USE_SPARK", "USE_KAFKA",
            "USE_ICEBERG", "AUTO_REFRESH_ON_START", "AUTO_REFRESH_INTERVAL_SECONDS",
            "GEMINI_API_KEY", "LLM_PROVIDER",
        ]
        payload["vietnam_realtime"] = {
            "ws_provider": "SSI iBoard (wss://iboard-pushstream.ssi.com.vn/realtime)",
            "boards": ["MAIN (HOSE)", "HNX", "UPCOM"],
            "opt_in": "VN_WS_ENABLED=true (mặc định) + Kafka streaming",
        }

    return payload


def get_storage_stats(layer: str = "all") -> dict[str, Any]:
    """Thống kê MinIO (hoặc local storage): số object, kích thước, tỉ lệ giữa các layer.

    Dùng để trả lời "Bronze có bao nhiêu parquet file?" hoặc "toàn bộ
    lakehouse chiếm bao nhiêu dung lượng?".
    """
    layer = (layer or "all").lower().strip()
    layers = (
        ("bronze", "stock-bronze"),
        ("silver", "stock-silver"),
        ("gold", "stock-gold"),
        ("models", "stock-models"),
        ("backtests", "stock-backtests"),
        ("silver_news", "stock-silver-news"),
        ("silver_fundamentals", "stock-silver-fundamentals"),
        ("gold_features", "stock-gold-features"),
    )

    storage = get_storage_backend()
    backend_name = storage.backend_name

    payload: dict[str, Any] = {
        "storage_backend": backend_name,
        "layer": layer,
        "buckets": {},
        "summary": {"total_objects": 0, "layers_with_data": 0},
    }

    # The MinIO backend has a method that returns both count + size; the local
    # backend exposes count_objects only. We degrade gracefully per layer.
    def _stats_for(name: str) -> dict[str, Any]:
        try:
            count = int(storage.count_objects(name, ""))
        except Exception as exc:  # noqa: BLE001
            return {"count": -1, "error": str(exc)}
        info: dict[str, Any] = {"count": count}
        # MinIO exposes bucket-level size through list_objects; try it best-effort.
        try:
            bucket = getattr(storage, "_bucket", lambda _n: None)(name)
            if bucket and backend_name == "minio":
                client = getattr(storage, "client", None)
                if client is not None:
                    total_bytes = 0
                    for obj in client.list_objects(bucket, prefix="", recursive=True):
                        total_bytes += int(getattr(obj, "size", 0) or 0)
                    info["total_bytes"] = total_bytes
                    info["size_mb"] = round(total_bytes / (1024 * 1024), 2)
        except Exception as exc:  # noqa: BLE001
            info["size_error"] = str(exc)
        return info

    target_layers = (
        [name for name, _ in layers]
        if layer == "all"
        else [layer]
    )

    for name in target_layers:
        stats = _stats_for(name)
        payload["buckets"][name] = stats
        c = stats.get("count", -1)
        if c and c > 0:
            payload["summary"]["total_objects"] += c
            payload["summary"]["layers_with_data"] += 1

    # Add a lightweight live sample from the layer record_count wrappers —
    # these count symbol=* prefixes in the actual lakehouse zone, so they're
    # the most accurate count of "symbols that have at least one partition".
    try:
        payload["live_counts"] = {
            "bronze_symbols": BronzeLayer().record_count(),
            "silver_symbols": SilverLayer().record_count(),
            "gold_symbols": GoldLayer().record_count(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("live_counts failed: %s", exc)

    # Surface MySQL status so the LLM can mention it if relevant
    payload["mysql_connected"] = bool(check_database_connection())

    return payload