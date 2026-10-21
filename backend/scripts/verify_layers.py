#!/usr/bin/env python3
"""Verify the three Medallion layers in object storage.

Reports per-layer object/symbol/byte counts and a per-symbol partition matrix
so you can tell "this ticker was never ingested" apart from "this ticker was
ingested but the Silver/Gold rebuild was skipped".

The prefix helper below is deliberate. S3/MinIO prefix matching is raw string
matching, so ``symbol=M`` also matches ``symbol=MA/``, ``symbol=MCD/``,
``symbol=META/`` and friends. Without terminating the prefix at the directory
boundary, reading Macy's silently returns a blend of 51 tickers. Always build
the prefix through :func:`symbol_prefix`.

Usage:
    python scripts/verify_layers.py
    python scripts/verify_layers.py --symbols AAPL MSFT NVDA
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable

from minio import Minio

DEFAULT_BUCKETS = ("stock-bronze", "stock-silver", "stock-gold")
DEFAULT_SYMBOLS = (
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "WMT",
    "XOM",
    "M",
    "MA",
    "VNM",
    "VCB",
)


def symbol_prefix(symbol: str) -> str:
    """Return the storage prefix for one symbol, terminated at the path boundary.

    The trailing slash is what stops ``symbol=M`` from also matching ``symbol=MA/``.
    """
    return f"symbol={symbol.strip().upper()}/"


def build_client(endpoint: str, access_key: str, secret_key: str, secure: bool) -> Minio:
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def count_objects(client: Minio, bucket: str, prefix: str = "") -> int:
    return sum(1 for _ in client.list_objects(bucket, prefix=prefix, recursive=True))


def bucket_symbols(client: Minio, bucket: str) -> set[str]:
    """Return the set of symbols present under ``symbol=`` in a bucket."""
    symbols: set[str] = set()
    for obj in client.list_objects(bucket, recursive=True):
        head = obj.object_name.split("/", 1)[0]
        if head.startswith("symbol="):
            symbols.add(head.split("=", 1)[1])
    return symbols


def summarize(client: Minio, buckets: Iterable[str]) -> tuple[int, int, set[str]]:
    """Print a per-layer summary and return (total_bytes, total_symbols, all_symbols)."""
    total_bytes = 0
    all_symbols: set[str] = set()
    print("layer summary")
    for bucket in buckets:
        objects = list(client.list_objects(bucket, recursive=True))
        size = sum(o.size or 0 for o in objects)
        symbols = bucket_symbols(client, bucket)
        total_bytes += size
        all_symbols |= symbols
        print(
            f"  {bucket:14s} {len(objects):7d} objects  "
            f"{len(symbols):4d} symbols  {size / 1024**3:6.2f} GB"
        )
    print(
        f"  {'TOTAL':14s} {'':7s}            {len(all_symbols):4d} symbols  "
        f"{total_bytes / 1024**3:6.2f} GB"
    )
    return total_bytes, len(all_symbols), all_symbols


def symbol_matrix(client: Minio, buckets: tuple[str, ...], symbols: tuple[str, ...]) -> list[str]:
    """Print the per-symbol partition matrix and return the missing entries."""
    print()
    print("objects per key symbol (partition count)")
    header = f"  {'SYMBOL':<8}" + "".join(f"{b.replace('stock-', '').upper():>10}" for b in buckets)
    print(header)
    print("  " + "-" * (len(header) - 2))

    missing: list[str] = []
    for symbol in symbols:
        counts = [count_objects(client, b, symbol_prefix(symbol)) for b in buckets]
        for bucket, n in zip(buckets, counts):
            if n == 0:
                missing.append(f"{symbol}:{bucket}")
        row = "".join(f"{(str(c) if c else 'MISSING'):>10}" for c in counts)
        print(f"  {symbol:<8}{row}")

    if missing:
        print(f"\n  MISSING -> {', '.join(missing)}")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--endpoint", default="127.0.0.1:9000", help="MinIO endpoint (host:port)")
    parser.add_argument("--access-key", default="minioadmin")
    parser.add_argument("--secret-key", default="minioadmin")
    parser.add_argument("--secure", action="store_true", help="Use HTTPS instead of HTTP")
    parser.add_argument("--buckets", nargs="+", default=list(DEFAULT_BUCKETS))
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    args = parser.parse_args(argv)

    client = build_client(args.endpoint, args.access_key, args.secret_key, args.secure)

    try:
        if not client.bucket_exists(args.buckets[0]):
            print(f"ERROR: bucket {args.buckets[0]} is not reachable at {args.endpoint}")
            print("       If MinIO lives in WSL2, check that the VM is still running:")
            print("         wsl --list --verbose")
            return 2
    except Exception as exc:  # noqa: BLE001 - surface the transport error verbatim
        print(f"ERROR: cannot reach MinIO at {args.endpoint}: {exc}")
        return 2

    buckets = tuple(args.buckets)
    summarize(client, buckets)
    missing = symbol_matrix(client, buckets, tuple(args.symbols))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
