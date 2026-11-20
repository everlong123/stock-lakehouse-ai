"""Build every Anki deck in this project from its JSON content file.

WHY A BUILD SCRIPT
------------------
An ``.apkg`` file is a ZIP holding a SQLite database with a fixed schema and
a set of GUIDs that must be internally consistent. Writing one by hand is
error-prone, so the project keeps:

    anki/content/dNN_<slug>.json   - the cards (human-editable, diffable)
    anki/deck_builder.py           - the shared model, CSS and template
    anki/build_all.py              - this script

Running ``python anki/build_all.py`` regenerates every ``.apkg`` into
``anki/build/``.

WHY THE DECK IDs AND NOTE GUIDS ARE CONSTANTS
---------------------------------------------
Anki identifies a deck by its ``deck_id`` and a note by its GUID. Both are
baked into the source (``DECKS`` in ``deck_builder.py`` and ``note_guid()``)
rather than generated per run. That means re-running this script UPDATES the
existing decks in Anki instead of creating duplicates, and the review
scheduling of every card survives.

RUN
---
    backend\\.venv\\Scripts\\python.exe anki\\build_all.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTENT_DIR = HERE / "content"
BUILD_DIR = HERE / "build"

sys.path.insert(0, str(HERE))

from deck_builder import DECKS, DeckBuilder  # noqa: E402


def load_content(path: Path) -> dict:
    """Load one content file, with a clear error when it is malformed."""
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path.name} is not valid JSON: {exc}\n"
            "Run 'python anki/repair_json.py' to repair raw quotes."
        ) from exc


def main() -> int:
    if not CONTENT_DIR.exists():
        print(f"No content directory at {CONTENT_DIR}")
        return 1

    content_files = sorted(CONTENT_DIR.glob("d*.json"))
    if not content_files:
        print(f"No deck content files in {CONTENT_DIR}")
        return 1

    total_cards = 0
    built: list[tuple[str, Path, int]] = []
    failures = 0

    for path in content_files:
        payload = load_content(path)
        slug = payload.get("deck", "")
        notes = payload.get("notes", [])

        if slug not in DECKS:
            print(f"FAIL {path.name}: unknown deck slug {slug!r}")
            failures += 1
            continue

        try:
            builder = DeckBuilder(slug)
            for note in notes:
                builder.add(
                    term=note["term"],
                    answer=note["answer"],
                    code=note.get("code", ""),
                    tags=note.get("tags", ""),
                )
            out = builder.write(BUILD_DIR)
        except (KeyError, ValueError) as exc:
            print(f"FAIL {path.name}: {exc}")
            failures += 1
            continue

        total_cards += builder.count
        built.append((slug, out, builder.count))
        print(f"OK   {path.name} -> {out.name} ({builder.count} cards)")

    print()
    print(f"Built {len(built)} decks, {total_cards} cards total")
    print(f"Output: {BUILD_DIR}")

    if failures:
        print(f"{failures} deck(s) FAILED")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
