"""Abstract object/file storage used by the lakehouse."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from io import BytesIO

import pandas as pd


class StorageBackend(ABC):
    """Read/write Parquet datasets for Bronze, Silver, and Gold."""

    backend_name: str = "abstract"

    @abstractmethod
    def write_parquet(self, layer: str, relative_path: str, frame: pd.DataFrame) -> str:
        """Persist a DataFrame as Parquet and return the storage path."""

    @abstractmethod
    def read_parquet(self, layer: str, relative_path: str) -> pd.DataFrame:
        """Read a single Parquet object."""

    @abstractmethod
    def read_prefix(self, layer: str, prefix: str) -> pd.DataFrame:
        """Read and concatenate all Parquet files under a prefix."""

    def read_prefix_window(
        self,
        layer: str,
        prefix: str,
        since: date | None = None,
        until: date | None = None,
    ) -> pd.DataFrame:
        """Read the partitions of a prefix that can hold a date range.

        WHY THIS EXISTS
        ---------------
        A ten-year daily symbol is stored as ~121 monthly partitions. A
        request for "the last six months" needs six of them, and the
        other 115 are downloaded, parsed and thrown away. The request
        cost is therefore set by the symbol's HISTORY rather than by the
        window the caller asked for.

        The default implementation reads everything, so a backend that
        does not know how to skip partitions still behaves correctly -
        just not quickly.
        """
        return self.read_prefix(layer, prefix)

    @abstractmethod
    def list_objects(self, layer: str, prefix: str = "") -> list[str]:
        """List object keys under a prefix."""

    def read_newest_partition(self, layer: str, prefix: str) -> pd.DataFrame:
        """Read ONLY the newest Parquet partition(s) under a prefix.

        WHY THIS EXISTS
        ---------------
        A ten-year daily symbol is stored as ~121 monthly partitions. A
        caller that wants "the newest bar" - the market tape, the
        latest-price endpoint - only needs the LAST of them.

        Reading the whole history for that cost ~1 s per symbol and
        ~11.7 s for the ten-symbol tape, measured 14/11/2026. Reading
        the newest partition costs a listing plus one object download.

        The partition keys carry their period in the path
        (``year=2026/month=11/...``), so the lexicographic order of
        the keys IS the chronological order - the newest key is the
        newest data.

        TWO partitions are read, not one. The change percentage needs the
        PREVIOUS close, and on the first trading day of a month the
        newest partition holds a single bar - reading one partition
        would report a 0.00% change on a day the stock actually moved.
        The second partition supplies the previous session's close, so
        the figure is the same one the full history reports.

        The default implementation returns an empty frame, so a backend
        that cannot do it still behaves correctly - just not quickly.
        """
        try:
            keys = [
                key
                for key in self.list_objects(layer, prefix)
                if key.endswith(".parquet")
            ]
        except Exception:  # noqa: BLE001 - never fail a "latest bar" read over a listing
            return pd.DataFrame()

        frames: list[pd.DataFrame] = []
        for key in sorted(keys, reverse=True)[:2]:
            try:
                frame = self.read_parquet(layer, key)
            except Exception:  # noqa: BLE001 - try the previous partition
                continue
            if frame is not None and not frame.empty:
                frames.append(frame)
            if len(frames) >= 2:
                break
        if not frames:
            return pd.DataFrame()
        if len(frames) == 1:
            return frames[0]
        return pd.concat(frames, ignore_index=True)

    @abstractmethod
    def exists(self, layer: str, relative_path: str) -> bool:
        """Return True if the object exists."""

    @abstractmethod
    def write_json(self, layer: str, relative_path: str, payload: dict) -> str:
        """Persist a JSON metadata document."""

    @abstractmethod
    def read_json(self, layer: str, relative_path: str) -> dict:
        """Read a JSON metadata document."""

    @abstractmethod
    def count_objects(self, layer: str, prefix: str = "") -> int:
        """Count objects under a prefix."""

    def health(self) -> dict[str, str | bool]:
        """Return a status payload for the System Status page."""
        return {"backend": self.backend_name, "available": True}


def dataframe_to_parquet_bytes(frame: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to Parquet bytes."""
    buffer = BytesIO()
    frame.to_parquet(buffer, engine="pyarrow", index=False)
    return buffer.getvalue()


def parquet_bytes_to_dataframe(payload: bytes) -> pd.DataFrame:
    """Deserialize Parquet bytes into a DataFrame."""
    return pd.read_parquet(BytesIO(payload), engine="pyarrow")
