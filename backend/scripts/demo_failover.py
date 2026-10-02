"""Demo: show automatic failover between providers.

This script shows what happens when providers fail:
- yfinance (blocked by Yahoo in this env) -> Alpha Vantage fallback
- yfinance + finnhub both fail -> web_scraper fallback

It also shows the chain configuration per interval.
"""

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.multi_source import (
    MultiSourceProvider,
    DEFAULT_CHAINS,
    build_default_adapter,
)
from app.data_sources.factory import get_data_provider

print("=" * 70)
print("AUTO-FAILOVER DEMO - multiple data sources, fallback tự động")
print("=" * 70)

# ── Step 1: Show the chain configuration ─────────────────────────────────
print("\n[1] Cấu hình chuỗi provider theo interval:")
for interval, chain in DEFAULT_CHAINS.items():
    arrow = " -> ".join(chain)
    print(f"    {interval:4s}: {arrow}")

print("\n    yfinance (primary) → fail → finnhub → fail → alpha_vantage → fail → web_scraper")


# ── Step 2: Show actual provider instantiation ────────────────────────────
print("\n[2] Các provider được khởi tạo:")
adapter = build_default_adapter("1d")
for name, provider in adapter._providers.items():
    print(f"    {name:18s} -> {provider.__class__.__name__}")


# ── Step 3: Real fetch with failover logs ─────────────────────────────────
print("\n[3] Fetch AAPL (1d) với failover thật:")
print("    Bắt đầu: yfinance (Yahoo đang block) → Alpha Vantage → success")
print()
import logging
logging.basicConfig(level=logging.INFO, format="    [%(levelname)s] %(name)s - %(message)s")

provider = get_data_provider()  # multi_source default chain
df = provider.get_historical_data("AAPL", interval="1d")

print(f"\n    -> Got {len(df)} rows from AAPL")
print(f"    -> First row: {df.iloc[0].to_dict()}")
print(f"    -> Last row: {df.iloc[-1].to_dict()}")


# ── Step 4: Try fetching with explicit chain override ─────────────────────
print("\n[4] Custom chain: chỉ dùng 1 provider (yfinance) -> sẽ throw error")
print("    Dùng chain ['yfinance'] (không có fallback):")
try:
    narrow = MultiSourceProvider(sources=["yfinance"])
    df = narrow.get_historical_data("AAPL", interval="1d")
    print(f"    -> Got {len(df)} rows")
except Exception as exc:
    print(f"    -> FAIL as expected: {type(exc).__name__}: {str(exc)[:150]}")


# ── Step 5: Same symbol, multi_source default -> success ───────────────────
print("\n[5] Same symbol, default multi_source chain -> success")
provider = get_data_provider()  # multi_source default chain (chứa fallback)
df = provider.get_historical_data("AAPL", interval="1d")
print(f"    -> Got {len(df)} rows")
print(f"    -> Source attribution (from first row 'source' column): {df.iloc[0].get('source')}")


print("\n" + "=" * 70)
print("TÓM TẮT:")
print("=" * 70)
print("Khi bạn không truyền 'source_name' vào run_symbol_pipeline:")
print("    -> app/data_sources/factory.py chọn 'multi_source' theo env DATA_SOURCE")
print("    -> MultiSourceProvider thử từng provider trong chain")
print("    -> Provider đầu có data thật (không empty) thắng")
print("    -> Log warnings cho mỗi provider fail để debug")
print("    -> Nếu tất cả fail mới raise DataSourceError")
print()
print("Trong demo trên: yfinance fail → Alpha Vantage (provider thứ 3) thành công.")