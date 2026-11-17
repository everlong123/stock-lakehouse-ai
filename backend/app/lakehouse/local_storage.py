"""Local filesystem storage backend for offline demos."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.logging_config import get_logger
from app.lakehouse.parquet_manager import filter_keys_by_window
from app.lakehouse.storage_base import StorageBackend

logger = get_logger(__name__)

LAYER_FOLDERS = {
    "bronze": "bronze",
    "silver": "silver",
    "gold": "gold",
    "models": "models",
    "backtests": "backtests",
    "quality": "quality",
    # Secondary layers from specialised Lakehouse modules. Each lives under
    # its own subfolder so reads via ``read_prefix`` stay scoped.
    "silver_fundamentals": "silver_fundamentals",
}


class LocalStorageBackend(StorageBackend):
    """Store lakehouse datasets under backend/data."""

    backend_name = "local"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.data_root_path
        for folder in LAYER_FOLDERS.values():
            (self.root / folder).mkdir(parents=True, exist_ok=True)

    def _path(self, layer: str, relative_path: str) -> Path:
        if layer not in LAYER_FOLDERS:
            raise StorageError(f"Unknown lakehouse layer: {layer}")
        return self.root / LAYER_FOLDERS[layer] / relative_path.replace("\\", "/")

    def write_parquet(self, layer: str, relative_path: str, frame: pd.DataFrame) -> str:
        path = self._path(layer, relative_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, engine="pyarrow", index=False)
        except Exception as exc:
            raise StorageError(f"Failed to write parquet {path}: {exc}") from exc
        logger.debug("Wrote %s rows to %s", len(frame), path)
        return str(path)

    def read_parquet(self, layer: str, relative_path: str) -> pd.DataFrame:
        path = self._path(layer, relative_path)
        if not path.exists():
            raise StorageError(f"Parquet file not found: {path}")
        return pd.read_parquet(path, engine="pyarrow")

    def read_prefix(self, layer: str, prefix: str) -> pd.DataFrame:
        base = self._path(layer, prefix)
        files = sorted(base.rglob("*.parquet")) if base.exists() else []
        if not files:
            return pd.DataFrame()
        frames = [pd.read_parquet(file, engine="pyarrow") for file in files]
        return pd.concat(frames, ignore_index=True)

    def read_prefix_window(
        self,
        layer: str,
        prefix: str,
        since: date | None = None,
        until: date | None = None,
    ) -> pd.DataFrame:
        """Read only the partitions that can hold the requested window.

        WHY THIS EXISTS
        ---------------
        The symbol's history is split into monthly partitions, and a
        request for a six-month window needs six of them. Reading the
        other 115 made the request cost scale with the symbol's HISTORY
        rather than with the window the caller asked for.
        """
        if since is None and until is None:
            return self.read_prefix(layer, prefix)

        base = self._path(layer, prefix)
        files = sorted(base.rglob("*.parquet")) if base.exists() else []
        if not files:
            return pd.DataFrame()

        # The local paths carry the same `year=.../month=.../` shape as
        # the object keys, so the same filter applies.
        keys = [str(file.relative_to(self._path(layer, ""))).replace("\\", "/") for file in files]
        selected = filter_keys_by_window(keys, since=since, until=until)
        if not selected:
            return pd.DataFrame()
        chosen = set(selected)
        frames = [
            pd.read_parquet(file, engine="pyarrow")
            for file, key in zip(files, keys)
            if key in chosen
        ]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def list_objects(self, layer: str, prefix: str = "") -> list[str]:
        """List the layer's files under ``prefix``.

        WHY THE PREFIX IS NOT TREATED AS A DIRECTORY
        ---------------------------------------------
        On MinIO a prefix is a plain string, so ``"symbol="`` matches every
        object whose key starts with it. On a filesystem there is no such
        thing: ``<root>/bronze/symbol=`` is not a directory, so treating
        the prefix as a path returned an EMPTY list. The quality gate then
        reported "the lakehouse holds no symbols" and audited NOTHING,
        without a single error.

        So the prefix is matched against each candidate path's own
        ``<layer>/``-relative form, which is what a prefix means on MinIO.
        """
        base = self._path(layer, "")
        if not base.exists():
            return []
        if prefix:
            needle = prefix.replace("\\", "/")
            files = []
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(base).as_posix()
                if relative.startswith(needle):
                    files.append(str(path))
            return files
        return [str(path) for path in sorted(base.rglob("*")) if path.is_file()]

    def exists(self, layer: str, relative_path: str) -> bool:
        return self._path(layer, relative_path).exists()

    def write_json(self, layer: str, relative_path: str, payload: dict) -> str:
        path = self._path(layer, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return str(path)

    def read_json(self, layer: str, relative_path: str) -> dict:
        path = self._path(layer, relative_path)
        if not path.exists():
            raise StorageError(f"JSON file not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def count_objects(self, layer: str, prefix: str = "") -> int:
        return len(self.list_objects(layer, prefix))
