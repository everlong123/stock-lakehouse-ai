"""
Transform Bronze data to Silver layer with PySpark (when USE_SPARK=true).

Usage: 
  python scripts/transform_to_silver.py --symbols AAPL MSFT --interval 1d
  USE_SPARK=true python scripts/transform_to_silver.py --interval 1d
"""

from __future__ import annotations

import sys
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import OHLCV_COLUMNS
from app.lakehouse import BronzeLayer, SilverLayer
from app.lakehouse.spark_session import spark_enabled, get_spark_session


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators to OHLCV data."""
    df = df.copy()
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Returns
    df["return_1d"] = df["close"].pct_change(1)
    df["return_5d"] = df["close"].pct_change(5)
    df["return_20d"] = df["close"].pct_change(20)
    
    # Moving averages
    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["sma_200"] = df["close"].rolling(200).mean()
    
    # Exponential moving averages
    df["ema_12"] = df["close"].ewm(span=12).mean()
    df["ema_26"] = df["close"].ewm(span=26).mean()
    
    # MACD
    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    
    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))
    
    # Bollinger Bands
    df["bb_middle"] = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_middle"] + 2 * bb_std
    df["bb_lower"] = df["bb_middle"] - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
    df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
    
    # ATR
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr_14"] = true_range.rolling(14).mean()
    
    # Volume indicators
    df["volume_sma_20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma_20"]
    
    # Volatility
    df["volatility_20d"] = df["return_1d"].rolling(20).std() * (252 ** 0.5)
    
    # Price relative to MAs
    df["price_to_sma_20"] = df["close"] / df["sma_20"]
    df["price_to_sma_50"] = df["close"] / df["sma_50"]
    df["price_to_sma_200"] = df["close"] / df["sma_200"]
    
    return df


def transform_symbol_spark(symbol: str, interval: str = "1d", lookback_days: int = 1825) -> dict:
    """Transform using PySpark for feature engineering."""
    bronze = BronzeLayer()
    silver = SilverLayer()
    
    # Read from bronze
    df = bronze.read(symbol)
    if df.empty:
        return {"symbol": symbol, "status": "no_data", "records": 0}
    
    # Filter by lookback
    start_date = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback_days)
    df = df[df["timestamp"] >= start_date]
    
    if df.empty:
        return {"symbol": symbol, "status": "no_data_after_filter", "records": 0}
    
    # Use SilverLayer transform (Spark when enabled)
    df_cleaned, quality = silver.transform(df)
    
    # Add technical indicators (still using pandas for this part)
    df_cleaned = add_technical_indicators(df_cleaned)
    
    # Write to silver
    metadata = silver.write(df_cleaned, quality)
    
    return {
        "symbol": symbol,
        "status": "success",
        "engine": quality.get("engine", "unknown"),
        "records": len(df_cleaned),
        "features": len(df_cleaned.columns),
        "date_range": f"{df_cleaned['timestamp'].min().date()} to {df_cleaned['timestamp'].max().date()}"
    }


def transform_symbol(symbol: str, interval: str = "1d", lookback_days: int = 1825) -> dict:
    """Transform bronze data for a single symbol."""
    return transform_symbol_spark(symbol, interval, lookback_days)


def main():
    parser = argparse.ArgumentParser(description="Transform Bronze to Silver layer (with PySpark)")
    parser.add_argument("--symbols", nargs="+", default=None, help="Symbols to transform (default: all in bronze)")
    parser.add_argument("--interval", default="1d", help="Data interval")
    parser.add_argument("--lookback", type=int, default=1825, help="Lookback days")
    args = parser.parse_args()
    
    # If no symbols specified, get all from bronze
    if args.symbols is None:
        bronze = BronzeLayer()
        from app.lakehouse.storage_factory import get_storage_backend
        storage = get_storage_backend()
        objects = storage.list_objects("bronze", "")
        symbols = set()
        for obj in objects:
            if obj.startswith("symbol="):
                parts = obj.replace("\\", "/").split("/")
                if parts:
                    symbol = parts[0].replace("symbol=", "")
                    symbols.add(symbol)
        args.symbols = sorted(symbols)
    
    engine = "PySpark" if spark_enabled() else "Pandas"
    
    print("=" * 60)
    print(f"BRONZE TO SILVER TRANSFORMATION ({engine})")
    print("=" * 60)
    print(f"Symbols: {len(args.symbols)}")
    print(f"Interval: {args.interval}")
    print(f"Lookback: {args.lookback} days")
    print(f"Engine: {engine}")
    print("=" * 60)
    
    results = []
    for symbol in args.symbols:
        print(f"\nTransforming {symbol}...", end=" ", flush=True)
        result = transform_symbol(symbol, args.interval, args.lookback)
        results.append(result)
        if result["status"] == "success":
            print(f"[OK] {result['records']} records, {result['features']} features ({result['engine']})")
        else:
            print(f"[FAIL] {result['status']}")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    successful = [r for r in results if r["status"] == "success"]
    print(f"Engine: {engine}")
    print(f"Successful: {len(successful)}/{len(results)}")
    total_records = sum(r["records"] for r in successful)
    print(f"Total records: {total_records}")


if __name__ == "__main__":
    main()
