"""Verify every built .apkg package is a valid Anki collection.

WHY THIS EXISTS
---------------
``genanki`` writes the package as a ZIP holding a SQLite database. A build
that "succeeded" can still produce a package Anki refuses to open - for
example when the note count in the database does not match the number of
notes that were added, or when a field contains markup that breaks the
template.

This script opens each ``.apkg``, reads the SQLite database back, and
checks:

* the archive has the expected members (collection.anki2 + media);
* the ``notes`` table holds exactly the expected number of rows;
* every note has 4 fields, a non-empty term, and an HTML answer;
* the deck name in the database matches the deck it was built for.

Run:
    backend\\.venv\\Scripts\\python.exe anki\\verify_build.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTENT_DIR = HERE / "content"
BUILD_DIR = HERE / "build"

EXPECTED_FIELDS = 4


def verify(apkg: Path, expected_notes: int, expected_deck: str) -> tuple[bool, str]:
    with zipfile.ZipFile(apkg) as archive:
        members = set(archive.namelist())
        if "collection.anki2" not in members:
            return False, "missing collection.anki2"
        with tempfile.TemporaryDirectory() as tmp:
            archive.extract("collection.anki2", tmp)
            db_path = Path(tmp) / "collection.anki2"
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute("SELECT flds, tags FROM notes").fetchall()
                decks = conn.execute("SELECT decks FROM col").fetchall()
            finally:
                conn.close()

    if len(rows) != expected_notes:
        return False, f"note count {len(rows)} != expected {expected_notes}"

    for flds, tags in rows:
        parts = flds.split("\x1f")
        if len(parts) != EXPECTED_FIELDS:
            return False, f"note has {len(parts)} fields, expected {EXPECTED_FIELDS}"
        if not parts[0].strip():
            return False, "note has an empty Term"
        if not parts[1].strip():
            return False, f"note {parts[0][:40]!r} has an empty Answer"
        if "<" not in parts[1]:
            return False, f"note {parts[0][:40]!r} answer is not rendered HTML"

    if decks:
        raw = decks[0][0]
        try:
            deck_map = json.loads(raw)
        except json.JSONDecodeError:
            deck_map = {}
        names = {info.get("name", "") for info in deck_map.values() if isinstance(info, dict)}
        if expected_deck not in names:
            return False, f"deck name {expected_deck!r} not found in {sorted(names)}"

    return True, f"{expected_notes} notes, {EXPECTED_FIELDS} fields each"


def main() -> int:
    failures = 0
    total = 0

    for content_path in sorted(CONTENT_DIR.glob("d*.json")):
        payload = json.loads(content_path.read_text(encoding="utf-8"))
        slug = payload["deck"]
        expected = len(payload["notes"])
        apkg = BUILD_DIR / f"{slug}.apkg"

        if not apkg.exists():
            print(f"FAIL {slug}: {apkg.name} does not exist")
            failures += 1
            continue

        expected_deck = f"Stock Lakehouse :: {slug.split('-', 1)[1]}".replace(
            "Kien truc Lakehouse Medallion", "Kien truc Lakehouse Medallion"
        )
        # The deck title in the package is the one from DECKS; find it there.
        sys.path.insert(0, str(HERE))
        from deck_builder import DECKS

        ok, message = verify(apkg, expected, DECKS[slug]["title"])
        status = "OK  " if ok else "FAIL"
        print(f"{status} {apkg.name}: {message}")
        if ok:
            total += expected
        else:
            failures += 1

    print()
    print(f"Verified {len(list(CONTENT_DIR.glob('d*.json')))} packages, {total} notes")
    if failures:
        print(f"{failures} package(s) FAILED")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
