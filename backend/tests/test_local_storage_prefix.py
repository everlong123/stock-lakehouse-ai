"""The local storage backend must answer a prefix the way MinIO answers it.

THE DEFECT THIS TEST PINS
--------------------------
``LocalStorageBackend.list_objects`` treated its ``prefix`` argument as a
DIRECTORY, so ``list_objects("bronze", "symbol=")`` looked for
``<root>/bronze/symbol=`` - a path that does not exist - and returned an
EMPTY list.

On MinIO a prefix is a plain string that is matched against the object key,
so the same call returns every symbol's partitions. The two backends
therefore answered the SAME question differently, and the quality gate -
which lists the Bronze bucket to discover the universe - reported "the
lakehouse holds no symbols" and audited NOTHING, without raising a single
error. A gate that silently checks zero symbols is indistinguishable from
a gate that says the data is clean.

The second half of the defect is the PATH SEPARATOR. MinIO keys look like
``symbol=AAPL/year=2026/month=11/part-001.parquet`` while the local backend
yields ``...\\bronze\\symbol=AAPL\\year=2026\\month=11\\part-001.parquet``.
The gate's index parser split on ``/`` only, so it produced an empty index
on the local backend even after the prefix was fixed.

These tests use a TEMPORARY directory and synthetic marker files. They
assert the LISTING BEHAVIOUR, never a market number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.quality_gate import _window_keys, lakehouse_symbols, partition_index  # noqa: E402
from app.lakehouse.local_storage import LocalStorageBackend  # noqa: E402


@pytest.fixture()
def local_store(tmp_path: Path) -> LocalStorageBackend:
    """A local backend holding three symbols' worth of partitions."""
    store = LocalStorageBackend(root=tmp_path)
    for symbol in ("AAPL", "CBA.AX", "MSFT"):
        partition = tmp_path / "bronze" / f"symbol={symbol}" / "year=2026" / "month=11"
        partition.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {
                "symbol": [symbol],
                "timestamp": pd.to_datetime(["2026-11-13 13:30:00Z"], utc=True),
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [1.0],
                "source": ["yahoo_http"],
            }
        ).to_parquet(partition / "part-001.parquet", index=False)
    return store


def test_prefix_lists_the_matching_files(local_store: LocalStorageBackend):
    objects = local_store.list_objects("bronze", "symbol=")
    assert objects, "a prefix must list the files beneath it"
    assert all("symbol=" in path for path in objects)


def test_prefix_is_scoped_to_the_named_symbol(local_store: LocalStorageBackend):
    objects = local_store.list_objects("bronze", "symbol=CBA.AX")
    assert objects
    assert all("symbol=CBA.AX" in path for path in objects)


def test_empty_prefix_lists_the_whole_layer(local_store: LocalStorageBackend):
    assert len(local_store.list_objects("bronze", "")) == 3


def test_unknown_prefix_lists_nothing(local_store: LocalStorageBackend):
    assert local_store.list_objects("bronze", "symbol=NOPE") == []


def test_partition_index_reads_the_local_paths(local_store: LocalStorageBackend):
    """The index must be built from the LOCAL path shape, not MinIO's."""
    index = partition_index(local_store, "bronze")
    assert set(index) == {"AAPL", "CBA.AX", "MSFT"}
    assert len(index["CBA.AX"]) == 1


def test_lakehouse_symbols_reads_the_local_paths(local_store: LocalStorageBackend):
    assert set(lakehouse_symbols(local_store)) == {"AAPL", "CBA.AX", "MSFT"}


def test_window_keys_find_the_period_in_a_local_path(local_store: LocalStorageBackend):
    """``year=``/``month=`` must be found behind a backslash too."""
    index = partition_index(local_store, "bronze")
    keys = index["CBA.AX"]
    assert _window_keys(keys, 3650), "the trailing window must keep a recent partition"
