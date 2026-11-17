"""No module may use a stdlib name it never imported.

WHY THIS TEST EXISTS
--------------------
On 15/11/2026 the quality gate failed with:

    Quality gate rotation could not be written to storage: name 'time' is
    not defined

`app/lakehouse/minio_storage.py` and `app/lakehouse/storage_factory.py`
both called `time.sleep()` inside their RETRY paths, and neither module
imported `time`. The bug was invisible while the network behaved, because
the retry path only runs when MinIO drops a connection - which is exactly
the moment the retry is needed.

A `NameError` on a retry path is the worst kind of bug: it converts a
recoverable network hiccup into a hard failure, and it is reported as
"the lakehouse is broken" rather than "the connection dropped".

HOW IT WORKS
------------
The AST of every module in `backend/` is parsed. The names the module
BINDS (imports, defs, assignments, arguments) are collected, the names it
READS are collected, and the difference is checked against the stdlib
names. A stdlib name that is read but never bound is a missing import.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: The stdlib modules whose names are checked. The list is short on
#: purpose: it holds the names a financial pipeline reaches for, and each
#: one of them has bitten this project at least once.
STDLIB_NAMES = frozenset(
    {
        "abc",
        "asyncio",
        "base64",
        "binascii",
        "bisect",
        "collections",
        "concurrent",
        "contextlib",
        "copy",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "functools",
        "glob",
        "gzip",
        "hashlib",
        "heapq",
        "io",
        "itertools",
        "json",
        "logging",
        "math",
        "multiprocessing",
        "operator",
        "os",
        "pathlib",
        "pickle",
        "queue",
        "random",
        "re",
        "secrets",
        "shutil",
        "signal",
        "socket",
        "sqlite3",
        "stat",
        "string",
        "struct",
        "subprocess",
        "sys",
        "tempfile",
        "textwrap",
        "threading",
        "time",
        "traceback",
        "types",
        "typing",
        "uuid",
        "warnings",
        "zipfile",
    }
)

#: The directories that are not ours.
#:
#: ``data`` is skipped on purpose: it holds the local copy of the lakehouse
#: (bronze/silver/gold/models) - hundreds of thousands of Parquet files.
#: Walking it takes minutes and there is never a hand-written ``.py`` file in
#: there, so including it only slows the test down and makes the collected
#: test count depend on how many data files happen to be on disk.
SKIP_PARTS = frozenset({".venv", "node_modules", "__pycache__", ".git", "data"})


def _python_files() -> list[Path]:
    """Every hand-written ``.py`` file in the backend.

    ``Path.rglob`` still WALKS into a skipped directory before filtering
    the result, so ``data/`` (hundreds of thousands of Parquet files) made
    this scan take over a hundred seconds. ``os.walk`` can prune a
    directory in place, so the skipped trees are never entered at all.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [name for name in dirnames if name not in SKIP_PARTS]
        for name in filenames:
            if name.endswith(".py"):
                found.append(Path(dirpath) / name)
    return sorted(found)


def _bound_names(tree: ast.AST) -> set[str]:
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
    return bound


def _used_names(tree: ast.AST) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_stdlib_name_is_used_without_being_imported(path: Path) -> None:
    """Every stdlib name a module READS must also be BOUND in that module."""
    source = path.read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - a broken file fails elsewhere
        pytest.skip(f"{path.name} does not parse as Python.")

    missing = sorted((_used_names(tree) - _bound_names(tree)) & STDLIB_NAMES)
    assert not missing, (
        f"{path.relative_to(ROOT)} uses {', '.join(missing)} without importing "
        "it. On a retry path that turns a recoverable network hiccup into a "
        "hard NameError."
    )
