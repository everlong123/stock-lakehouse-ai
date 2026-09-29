"""Script chạy batch ingestion cho VN stocks với scheduling đơn giản.

Dùng:
    python -m scripts.schedule_batch          # Chạy ngay lập tức
    python -m scripts.schedule_batch --daily  # Chạy hàng ngày lúc 18:00
    python -m scripts.schedule_batch --watch  # Chạy liên tục với interval
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Setup path
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.constants import VN_SYMBOLS
from app.core.logging_config import get_logger
from app.scripts.fetch_vn_stocks import fetch_vn_stock

logger = get_logger(__name__)


def run_batch(symbols: list[str] | None = None, dry_run: bool = False) -> dict:
    """Chạy batch cho tất cả symbols."""
    target_symbols = symbols or VN_SYMBOLS
    started = datetime.now(timezone.utc)

    logger.info(f"Batch started: {len(target_symbols)} symbols")
    print(f"\n{'='*50}")
    print(f"  BATCH INGESTION - {started.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    print(f"Symbols: {len(target_symbols)}")
    print(f"Dry run: {dry_run}")
    print(f"{'='*50}\n")

    results = {"success": [], "failed": [], "skipped": []}

    for i, symbol in enumerate(target_symbols, 1):
        print(f"[{i}/{len(target_symbols)}] {symbol}...", end=" ")

        if dry_run:
            print("SKIPPED (dry run)")
            results["skipped"].append(symbol)
            continue

        try:
            result = fetch_vn_stock(symbol)
            if result["status"] == "success":
                print(f"✅ {result['bronze_records']} records")
                results["success"].append(symbol)
            else:
                print(f"❌ {result.get('message', 'Lỗi')}")
                results["failed"].append(symbol)
        except Exception as e:
            print(f"❌ Error: {e}")
            results["failed"].append(symbol)
            logger.exception(f"Lỗi khi xử lý {symbol}")

        # Rate limit: chờ 2 giây giữa các request
        if i < len(target_symbols):
            time.sleep(2)

    finished = datetime.now(timezone.utc)
    elapsed = (finished - started).total_seconds()

    print(f"\n{'='*50}")
    print(f"  BATCH COMPLETE")
    print(f"{'='*50}")
    print(f"Thời gian: {elapsed:.1f}s")
    print(f"Thành công: {len(results['success'])}/{len(target_symbols)}")
    print(f"Thất bại: {len(results['failed'])}")

    if results["failed"]:
        print(f"\nSymbols thất bại: {', '.join(results['failed'])}")

    return {
        "started": started.isoformat(),
        "finished": finished.isoformat(),
        "elapsed_seconds": elapsed,
        "total": len(target_symbols),
        "success": len(results["success"]),
        "failed": len(results["failed"]),
        "failed_symbols": results["failed"],
    }


def run_scheduled(daily: bool = True, hour: int = 18, minute: int = 0) -> None:
    """Chạy batch theo lịch hàng ngày."""
    import schedule

    def job() -> None:
        logger.info("Scheduled batch job started")
        run_batch()

    if daily:
        schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(job)
        print(f"📅 Đã lên lịch: Chạy lúc {hour:02d}:{minute:02d} hàng ngày")
    else:
        # Chạy mỗi giờ
        schedule.every().hour.do(job)
        print("📅 Đã lên lịch: Chạy mỗi giờ")

    print("Nhấn Ctrl+C để dừng.\n")

    while True:
        schedule.run_pending()
        time.sleep(60)


def run_watch(interval_minutes: int = 60) -> None:
    """Chạy liên tục với interval."""
    print(f"👀 Watch mode: Chạy mỗi {interval_minutes} phút")
    print("Nhấn Ctrl+C để dừng.\n")

    while True:
        run_batch()
        print(f"\n⏳ Chờ {interval_minutes} phút...\n")
        time.sleep(interval_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="VN Stock Batch Ingestion Scheduler")
    parser.add_argument("--symbols", default=None, help="Symbols (cách nhau bằng dấu phẩy)")
    parser.add_argument("--dry-run", action="store_true", help="Không lấy data, chỉ kiểm tra")
    parser.add_argument("--daily", action="store_true", help="Chạy hàng ngày lúc 18:00")
    parser.add_argument("--hour", type=int, default=18, help="Giờ chạy (mặc định: 18)")
    parser.add_argument("--minute", type=int, default=0, help="Phút chạy (mặc định: 0)")
    parser.add_argument("--watch", action="store_true", help="Chạy liên tục")
    parser.add_argument("--interval", type=int, default=60, help="Interval (phút) cho watch mode")
    parser.add_argument("--once", action="store_true", help="Chạy một lần (mặc định)")

    args = parser.parse_args()

    # Parse symbols
    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    if args.daily or args.watch:
        # Schedule mode
        try:
            import schedule  # type: ignore
        except ImportError:
            print("❌ Cần cài schedule: pip install schedule")
            sys.exit(1)

        if args.watch:
            run_watch(args.interval)
        else:
            run_scheduled(hour=args.hour, minute=args.minute)
    else:
        # Run once
        run_batch(symbols=symbols, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
