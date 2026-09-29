"""Create the Iceberg REST catalog tables for the Medallion lakehouse.

Run this once after ``docker compose up -d`` when ``USE_ICEBERG=true``.
The script is idempotent - existing tables are left untouched.

    python scripts/init_iceberg_tables.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Iceberg tables (Bronze/Silver/Gold).")
    parser.add_argument("--layer", choices=["bronze", "silver", "gold", "all"], default="all")
    parser.add_argument("--namespace", default="lakehouse",
                        help="Catalog namespace (default: lakehouse).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    try:
        from app.lakehouse.iceberg_manager import IcebergManager
    except ImportError as exc:
        logger.error(
            "pyiceberg is not installed: %s\n"
            "Install via 'pip install pyiceberg>=0.7.0' to use this script.",
            exc,
        )
        sys.exit(1)

    manager = IcebergManager()
    if args.layer == "all":
        tables = manager.create_all_tables()
        for layer, table in tables.items():
            logger.info("✓ %s table ready: %s", layer, table.identifier)
        return

    method = getattr(manager, f"create_{args.layer}_table")
    table = method()
    logger.info("✓ %s table ready: %s", args.layer, table.identifier)


if __name__ == "__main__":
    main()