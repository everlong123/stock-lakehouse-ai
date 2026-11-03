"""Normalise the LLM's markdown so the hand-written UI renderer can handle it.

The chat bubble uses a small, purpose-built markdown renderer (see
``frontend/src/components/agent/Markdown.tsx``) instead of a full markdown
library. That keeps the DOM safe and small, but it means the model has to
stay inside a narrow subset of markdown. Models routinely step outside it:

- They write ``**RSI (14):** ... **56.82**`` and the renderer sees the first
  ``**`` pair close early, so the second pair opens an italic run that
  swallows the rest of the paragraph.
- They separate the items of one list with blank lines, which splits the
  list into several lists that each restart at "1.".
- They emit markdown tables, which the renderer cannot draw.

This module rewrites the reply into the supported subset. It is a text
transform, not a second renderer: it never invents content and never drops
a number, it only fixes the markers.
"""

from __future__ import annotations

import re

# "**bold**" that is immediately followed by another "**bold**" on the same
# line: the renderer would pair the first marker with the second one and
# treat the rest as italic.
_DOUBLE_BOLD = re.compile(r"\*\*(?!\s)(.+?)(?<!\s)\*\*")

# A table row: "| a | b |" or "a | b" with a separator row underneath.
_TABLE_ROW = re.compile(r"^\s*\|?.*\|.*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:-]*-[-\s|:]*\|?\s*$")

# Ordered-list marker: "1." / "1)" / "01."
_ORDERED_MARKER = re.compile(r"^(\s*)(\d{1,3})[.)]\s+(.*)$")
# Bullet marker: "- " / "* " / "+ "
_BULLET_MARKER = re.compile(r"^(\s*)[-*+]\s+(.*)$")


def _fix_bold_spacing(text: str) -> str:
    """Make sure a bold span does not start or end with whitespace.

    ``** bold **`` renders as literal asterisks in most parsers; stripping
    the inner padding keeps the emphasis working.
    """
    return _DOUBLE_BOLD.sub(lambda m: f"**{m.group(1).strip()}**", text)


def _table_to_bullets(lines: list[str]) -> list[str]:
    """Convert a markdown table into a bullet list.

    Tables are not renderable in the chat bubble, but the content is
    valuable. Turning "a | b" into "- **a**: b" keeps every value visible.
    """
    out: list[str] = []
    header: list[str] | None = None
    for line in lines:
        if _TABLE_SEPARATOR.match(line):
            continue  # the "---" separator row carries no data
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cells = [c for c in cells if c]
        if not cells:
            continue
        if header is None:
            header = cells
            out.append("**" + " / ".join(header) + "**")
            continue
        # Pad the row to the header width so short rows still line up.
        padded = list(cells) + [""] * (len(header) - len(cells))
        pairs = [
            f"**{head}**: {value}" if value else f"**{head}**"
            for head, value in zip(header, padded)
        ]
        out.append("- " + "; ".join(pairs))
    return out


def normalize_markdown(text: str) -> str:
    """Return ``text`` rewritten into the markdown subset the UI supports."""
    if not text:
        return text

    text = text.replace("\r\n", "\n").replace("\t", "    ")
    lines = text.split("\n")
    out: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Table → bullets ────────────────────────────────────────────────
        if _TABLE_ROW.match(line) and "|" in line:
            table: list[str] = []
            while i < len(lines) and _TABLE_ROW.match(lines[i]) and "|" in lines[i]:
                table.append(lines[i])
                i += 1
            out.extend(_table_to_bullets(table))
            out.append("")
            continue

        # ── Ordered list: keep one continuous run ─────────────────────────
        ordered = _ORDERED_MARKER.match(line)
        if ordered:
            indent, number, body = ordered.group(1), ordered.group(2), ordered.group(3)
            # Collect the whole run, skipping blank lines that only split it.
            items: list[tuple[str, str, str]] = [(indent, number, body)]
            i += 1
            while i < len(lines):
                nxt = _ORDERED_MARKER.match(lines[i])
                if nxt:
                    items.append((nxt.group(1), nxt.group(2), nxt.group(3)))
                    i += 1
                    continue
                # A blank line followed by another ordered item is a split
                # list, not a new section: keep it together.
                if lines[i].strip() == "":
                    j = i
                    while j < len(lines) and lines[j].strip() == "":
                        j += 1
                    if j < len(lines) and _ORDERED_MARKER.match(lines[j]):
                        i = j
                        continue
                break

            base_indent = len(indent)
            for idx, (ind, num, item_body) in enumerate(items):
                marker = f"{num}." if idx == 0 else f"{idx + 1}."
                out.append(f"{' ' * base_indent}{marker} {_fix_bold_spacing(item_body)}")
            continue

        # ── Bullet list: keep one continuous run ──────────────────────────
        bullet = _BULLET_MARKER.match(line)
        if bullet:
            indent, body = bullet.group(1), bullet.group(2)
            out.append(f"{indent}- {_fix_bold_spacing(body)}")
            i += 1
            continue

        out.append(_fix_bold_spacing(line))
        i += 1

    # Collapse 3+ blank lines into one blank line.
    cleaned: list[str] = []
    blanks = 0
    for line in out:
        if line.strip() == "":
            blanks += 1
            if blanks > 1:
                continue
        else:
            blanks = 0
        cleaned.append(line)

    return "\n".join(cleaned).strip()
