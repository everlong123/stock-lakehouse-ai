"""Shared Anki deck builder for the Stock Lakehouse project.

WHY A BUILDER INSTEAD OF HAND-WRITTEN .apkg FILES
-------------------------------------------------
An ``.apkg`` file is a ZIP holding a SQLite database with a fixed schema and
a set of GUIDs that must be internally consistent. Hand-writing one is
error-prone and unmaintainable. ``genanki`` handles that part; this module
adds the parts specific to this project:

* ONE stable GUID per deck, so re-running the build UPDATES the existing
  deck in Anki instead of creating a duplicate. Anki matches notes by
  note GUID, and the deck identity by deck ID, so both must be constants
  baked into the source rather than generated per run.
* A shared note model with the fields this project actually needs:
  ``Term`` (the question), ``Answer`` (the explanation), ``Code``
  (the file / function the knowledge lives in), and ``Tags``.
* A consistent HTML renderer, so a card written in one deck looks the same
  as a card written in another.

THE NOTE MODEL
--------------
``Term``       - front. The concept being asked about.
``Answer``     - back. The explanation, with the "why", not just the "what".
``Code``       - the concrete anchor: file path, function, endpoint, or
                 constant. This is what makes a card verifiable against the
                 repository instead of being a floating assertion.
``Tags``       - Anki tags, used for filtering and for building sub-decks.

FIELDS ARE PASSED AS A LIST, NOT A DICT
----------------------------------------
``genanki.Note`` indexes ``fields`` by position (``fields[model.sort_field_index]``)
when it computes the note's sort field. Passing a dict makes that indexing
raise ``KeyError: 0`` at package-write time - a long way from the mistake.

So the fields are always given as a list in the exact order the model
declares them, and the sort field is set explicitly to the term.

TEMPLATE
--------
The front template shows the term and asks for the explanation. The back
template reveals the answer plus the code anchor. A ``Concept`` hint field
is intentionally absent: adding a third line to the front dilutes the
question and makes the card harder to answer from memory.
"""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path
from typing import Iterable

import genanki

# ── Model ──────────────────────────────────────────────────────────────────────

#: The shared note model. The ``model_id`` is a constant on purpose: changing
#: it would orphan every existing note in every user's Anki collection.
MODEL_ID = 1607392319

#: The Anki deck template. The fields are wrapped in ``{{ }}`` so Anki's
#: template engine substitutes them at render time.
TEMPLATE = """{{FrontSide}}

<hr id=answer>

<div class=answer>
{{Answer}}
</div>

{{#Code}}
<div class=code>
<b>Code:</b> <code>{{Code}}</code>
</div>
{{/Code}}

{{#Tags}}
<div class=tags>
{{Tags}}
</div>
{{/Tags}}
"""

CSS = """.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 20px;
  text-align: left;
  color: #1c1c1e;
  background: #ffffff;
  padding: 20px;
  line-height: 1.5;
}

.front-term {
  font-size: 24px;
  font-weight: 650;
  color: #0b3d91;
  margin-bottom: 14px;
}

.answer {
  margin-top: 12px;
}

.answer p {
  margin: 0 0 10px 0;
}

.answer ul, .answer ol {
  margin: 0 0 10px 0;
  padding-left: 22px;
}

.answer li {
  margin-bottom: 5px;
}

.code {
  margin-top: 16px;
  padding: 10px 12px;
  background: #f4f6f9;
  border-left: 3px solid #0b3d91;
  border-radius: 4px;
  font-size: 15px;
}

.code code {
  background: transparent;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  color: #234;
}

.tags {
  margin-top: 12px;
  font-size: 13px;
  color: #8a8a8e;
  font-style: italic;
}

code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  background: #f0f2f5;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 0.9em;
}

strong { color: #0b3d91; }

table {
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 0.9em;
}

th, td {
  border: 1px solid #d5d9e0;
  padding: 5px 9px;
  text-align: left;
}

th { background: #f4f6f9; }
"""

MODEL = genanki.Model(
    MODEL_ID,
    "Stock Lakehouse - Concept (Term/Answer/Code)",
    fields=[
        {"name": "Term"},
        {"name": "Answer"},
        {"name": "Code"},
        {"name": "Tags"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": '<div class=front-term>{{Term}}</div>',
            "afmt": TEMPLATE,
        }
    ],
    css=CSS,
)


# ── Deck definitions ──────────────────────────────────────────────────────────

#: Every deck in the project, keyed by slug.
#:
#: The ``deck_id`` MUST be a constant. Anki uses it to identify the deck
#: across rebuilds: change it and Anki will treat the rebuild as a brand
#: new deck and you will end up with duplicates of everything.
DECKS: dict[str, dict[str, str]] = {
    "01-lakehouse-architecture": {
        "title": "Stock Lakehouse :: 01 - Kien truc Lakehouse Medallion",
        "deck_id": 1740110001,
    },
    "02-data-quality": {
        "title": "Stock Lakehouse :: 02 - Chat luong du lieu & Integrity",
        "deck_id": 1740110002,
    },
    "03-forecasting-models": {
        "title": "Stock Lakehouse :: 03 - Du bao & Mo hinh ML/DL",
        "deck_id": 1740110003,
    },
    "04-backtesting": {
        "title": "Stock Lakehouse :: 04 - Backtest & Walk-forward validation",
        "deck_id": 1740110004,
    },
    "05-technical-analysis": {
        "title": "Stock Lakehouse :: 05 - Phan tich ky thuat & Chi bao",
        "deck_id": 1740110005,
    },
    "06-ai-agent": {
        "title": "Stock Lakehouse :: 06 - AI Agent & Tool calling",
        "deck_id": 1740110006,
    },
    "07-trading-calendar": {
        "title": "Stock Lakehouse :: 07 - Lich giao dich & Quan ly phien",
        "deck_id": 1740110007,
    },
    "08-operations": {
        "title": "Stock Lakehouse :: 08 - Van hanh & Ha tang",
        "deck_id": 1740110008,
    },
    "09-data-sources-api": {
        "title": "Stock Lakehouse :: 09 - Nguon du lieu & API layer",
        "deck_id": 1740110009,
    },
    "10-database-ledger": {
        "title": "Stock Lakehouse :: 10 - Database, Alembic & Prediction ledger",
        "deck_id": 1740110010,
    },
    "11-frontend": {
        "title": "Stock Lakehouse :: 11 - Frontend, UI/UX & i18n",
        "deck_id": 1740110011,
    },
    "12-fundamentals-macro": {
        "title": "Stock Lakehouse :: 12 - Fundamental, Macro & Order book",
        "deck_id": 1740110012,
    },
}


# ── Rendering helpers ─────────────────────────────────────────────────────────

_CODE_RE = re.compile(r"`([^`]+)`")


def render(text: str) -> str:
    """Render a plain-text answer into the HTML Anki will display.

    The input is written in a small Markdown subset on purpose:

    * ``**bold**``            -> strong
    * `` `code` ``            -> inline code
    * ``- item``              -> bullet list (consecutive items group)
    * ``1. item``             -> numbered list
    * ``> quote``             -> blockquote (used for the "why")
    * ``---``                 -> horizontal rule (splits long answers)
    * blank line              -> paragraph break

    Tables are NOT part of the subset. A table in a card is wide, hard to
    read on a phone, and this project's facts are better expressed as
    short lists. The answer to "which indicators are there" is a list; a
    two-column table would wrap badly on every mobile screen.
    """
    if not text:
        return ""

    lines = text.strip().split("\n")
    out: list[str] = []
    list_kind: str | None = None
    para: list[str] = []

    def flush_para() -> None:
        if para:
            out.append("<p>" + "<br>".join(para) + "</p>")
            para.clear()

    def flush_list() -> None:
        nonlocal list_kind
        if list_kind == "ul":
            out.append("</ul>")
        elif list_kind == "ol":
            out.append("</ol>")
        list_kind = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_para()
            flush_list()
            continue

        if stripped == "---":
            flush_para()
            flush_list()
            out.append("<hr>")
            continue

        if stripped.startswith("> "):
            flush_para()
            flush_list()
            quote = stripped[2:].strip()
            out.append(f'<blockquote>{_inline(quote)}</blockquote>')
            continue

        # Bullet list
        if stripped.startswith("- ") or stripped.startswith("* "):
            flush_para()
            if list_kind != "ul":
                flush_list()
                out.append("<ul>")
                list_kind = "ul"
            out.append(f"<li>{_inline(stripped[2:].strip())}</li>")
            continue

        # Numbered list
        match = re.match(r"^(\d+)[.)]\s+(.*)$", stripped)
        if match:
            flush_para()
            if list_kind != "ol":
                flush_list()
                out.append("<ol>")
                list_kind = "ol"
            out.append(f"<li>{_inline(match.group(2).strip())}</li>")
            continue

        flush_list()
        para.append(_inline(stripped))

    flush_para()
    flush_list()

    return "\n".join(out)


def _inline(text: str) -> str:
    """Render the inline part of a line: bold and inline code."""
    # Escape first, then re-introduce the markup we generated ourselves.
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = _CODE_RE.sub(r"<code>\1</code>", escaped)
    return escaped


def note_guid(deck_slug: str, term: str) -> int:
    """A STABLE note GUID derived from the deck and the term.

    Why not a random GUID: Anki identifies a note by its GUID. If the GUID
    changes on every rebuild, every rebuild creates duplicate notes and the
    review history is thrown away. Deriving it from ``(deck, term)`` means
    a rebuilt deck updates the existing card in place and keeps the
    scheduling information.

    The 32-bit space is large enough here: a deck holds at most a few
    hundred notes, and a collision requires two identical terms in the
    same deck, which the content generator already forbids.
    """
    digest = hashlib.sha256(f"{deck_slug}::{term}".encode("utf-8")).digest()
    # Force a positive 31-bit-ish integer in Anki's GUID range.
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


class DeckBuilder:
    """Collect notes for one deck and write the ``.apkg``."""

    def __init__(self, slug: str) -> None:
        if slug not in DECKS:
            raise KeyError(f"Unknown deck slug: {slug}")
        meta = DECKS[slug]
        self.slug = slug
        self.deck = genanki.Deck(meta["deck_id"], meta["title"])
        self._terms: set[str] = set()
        self.count = 0

    def add(self, term: str, answer: str, code: str = "", tags: str = "") -> None:
        """Add one card. Duplicate terms within a deck are rejected loudly."""
        term = term.strip()
        if term in self._terms:
            raise ValueError(
                f"[{self.slug}] Duplicate term: {term!r}. "
                "Each concept must appear exactly once per deck."
            )
        self._terms.add(term)
        self.deck.add_note(
            genanki.Note(
                model=MODEL,
                guid=note_guid(self.slug, term),
                fields=[
                    term,
                    render(answer),
                    code.strip(),
                    tags.strip(),
                ],
                sort_field=term,
                tags=_tags_list(tags),
            )
        )
        self.count += 1

    def extend(self, notes: Iterable[tuple[str, str, str, str]]) -> None:
        """Add many cards from ``(term, answer, code, tags)`` tuples."""
        for term, answer, code, tags in notes:
            self.add(term, answer, code, tags)

    def write(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.slug}.apkg"
        genanki.Package(self.deck).write_to_file(path)
        return path


def _tags_list(tags: str) -> list[str]:
    """Split a tag string into Anki tags."""
    cleaned = [t.strip() for t in re.split(r"[\s,]+", tags) if t.strip()]
    return cleaned


def build_deck(slug: str, notes: Iterable[tuple[str, str, str, str]], out_dir: Path) -> tuple[Path, int]:
    """Build one deck from its note tuples. Returns ``(path, note_count)``."""
    builder = DeckBuilder(slug)
    builder.extend(notes)
    return builder.write(out_dir), builder.count
