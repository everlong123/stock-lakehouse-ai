import { Fragment, type ReactNode } from "react";

/**
 * Tiny safe-by-construction Markdown renderer for the AI agent chat bubble.
 *
 * We intentionally do NOT pull in a full markdown library — the agent
 * occasionally emits raw, half-formed markdown (unmatched asterisks, stray
 * backticks, broken tables) and a real parser would either crash the page or
 * leak those literal characters back into the DOM. This renderer:
 *
 * - parses into an AST once (decodes pre-escaped HTML entities in raw text)
 * - handles the markdown the LLM actually emits in this app
 *   (headings, paragraphs, bold, italic, inline + fenced code, bullet lists,
 *   numbered lists, nested lists, blockquotes and horizontal rules)
 * - leaves the original text visible for any construct it does not know,
 *   so a malformed reply never produces a blank bubble
 */

const HTML_ENTITY_DECODES: ReadonlyArray<readonly [string, string]> = [
    ["&amp;", "&"],
  ["&lt;", "<"],
  ["&gt;", ">"],
  ["&quot;", '"'],
  ["&apos;", "'"],
  ["&nbsp;", " "],
];

function unescapeHtmlEntities(text: string): string {
  let out = text;
    for (const [needle, replacement] of HTML_ENTITY_DECODES) {
    out = out.split(needle).join(replacement);
  }
  return out;
}

// React text nodes do NOT decode HTML entities — they render whatever string
// we hand them, character for character. So an LLM that emits `&amp;` ends up
// displayed as the literal text "&amp;" unless we decode it ourselves.
//
// XSS safety is unaffected: React escapes `<`, `>`, and `&` *when it parses
// JSX into the DOM*, but text nodes set via `{value}` (or our dangerously-
// rendered AST) are inserted with `textContent`, never as HTML. So we only
// need to decode the entities the model pre-escaped, not re-escape anything.
function escapeHtml(text: string): string {
  return unescapeHtmlEntities(text);
}

type ListItem = {
  /** Inline text of the item itself (the "1." / "-" marker is stripped). */
  text: string;
  /** Nested blocks (sub-lists) that belong to this item. */
  children: Block[];
};

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; lang: string | null; content: string }
  | { kind: "quote"; text: string }
  | { kind: "hr" }
  | { kind: "list"; ordered: boolean; start: number; items: ListItem[] };

// ── List markers ──────────────────────────────────────────────────────────
// A bullet needs whitespace after the marker so that emphasis such as
// "**bold**" at the start of a line is not mistaken for a bullet.
const BULLET_RE = /^(\s*)[-*+]\s+(.*)$/;
const ORDERED_RE = /^(\s*)(\d{1,3})[.)]\s+(.*)$/;
// "---", "***", "___" (at least three of the same character).
const HR_RE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;

type Marker = {
  indent: number;
  ordered: boolean;
  number: number;
  text: string;
};

function matchMarker(line: string): Marker | null {
  const ordered = ORDERED_RE.exec(line);
  if (ordered) {
    return {
      indent: ordered[1].length,
      ordered: true,
      number: Number(ordered[2]),
      text: ordered[3],
    };
  }
  const bullet = BULLET_RE.exec(line);
  if (bullet) {
    return { indent: bullet[1].length, ordered: false, number: 1, text: bullet[2] };
  }
  return null;
}

/**
 * Parse a (possibly nested) list starting at `start`.
 *
 * Returns the list block plus the index of the first line that is NOT part of
 * the list. Two things this fixes versus a flat line-by-line parser:
 *
 * 1. **Numbering.** "1. a", "2. b", "3. c" used to become three separate
 *    `<ol>` elements, each restarting at 1 — the user saw "1. 1. 1.".
 *    Consecutive markers are now one list with a `start` offset.
 * 2. **Continuation lines.** A sub-bullet indented under a numbered item
 *    ("   - detail") used to break the list and be merged into the following
 *    paragraph, which glued two unrelated sentences together with a space
 *    and swallowed the line break.
 */
function parseList(
  lines: string[],
  start: number,
): { block: Block; next: number } {
  const first = matchMarker(lines[start]);
  if (!first) {
    return { block: { kind: "paragraph", text: lines[start] ?? "" }, next: start + 1 };
  }

  const baseIndent = first.indent;
  const items: ListItem[] = [];
  let i = start;

  while (i < lines.length) {
    const marker = matchMarker(lines[i]);
    if (!marker) break;
    // A deeper marker here means the previous item owns it, not this loop.
    if (marker.indent > baseIndent) break;
    if (marker.indent < baseIndent) break;

    const item: ListItem = { text: marker.text, children: [] };
    i += 1;

    // Absorb the body of this item: nested lists and continuation lines.
    while (i < lines.length) {
      const line = lines[i];
      if (line.trim() === "") break;

      const nested = matchMarker(line);
      if (nested && nested.indent <= baseIndent) break; // next sibling item
      if (nested && nested.indent > baseIndent) {
        // Sub-list belonging to this item.
        const sub = parseList(lines, i);
        item.children.push(sub.block);
        i = sub.next;
        continue;
      }
      if (/^\s{2,}\S/.test(line)) {
        // Soft continuation of the item's own text.
        item.text = item.text ? `${item.text} ${line.trim()}` : line.trim();
        i += 1;
        continue;
      }
      break; // dedented plain line — the list is over
    }

    items.push(item);
  }

  return {
    block: {
      kind: "list",
      ordered: first.ordered,
      start: first.ordered ? first.number : 1,
      items,
    },
    next: i,
  };
}

function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const rawLine = lines[i];
    const line = rawLine;

    // Skip blank lines between blocks.
    if (line.trim() === "") {
      i += 1;
      continue;
    }

    // Horizontal rule.
    if (HR_RE.test(line)) {
      blocks.push({ kind: "hr" });
      i += 1;
      continue;
    }

    // Fenced code block: ```lang ... ```
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim() || null;
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1; // skip closing fence
      blocks.push({ kind: "code", lang, content: buf.join("\n") });
      continue;
    }

    // Headings: # / ## / ###
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length as 1 | 2 | 3;
      blocks.push({ kind: "heading", level, text: heading[2].trim() });
      i += 1;
      continue;
    }

    // Blockquote: > ...
    if (line.startsWith(">")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].startsWith(">")) {
        buf.push(lines[i].replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ kind: "quote", text: buf.join("\n") });
      continue;
    }

    // List (bullet or ordered), including nested items.
    const marker = matchMarker(line);
    if (marker && marker.indent <= 3) {
      const { block, next } = parseList(lines, i);
      blocks.push(block);
      i = next;
      continue;
    }

    // Paragraph: collect until blank line / block boundary.
    const buf: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("```") &&
      !/^#{1,3}\s+/.test(lines[i]) &&
      !lines[i].startsWith(">") &&
      !HR_RE.test(lines[i]) &&
      !(matchMarker(lines[i]) && (matchMarker(lines[i]) as Marker).indent <= 3)
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: buf.join(" ") });
  }

  return blocks;
}

/**
 * Render inline markdown.
 *
 * The scan is character-by-character on purpose. An earlier version jumped
 * straight to the next `*` or `` ` `` and emitted it as a literal when no
 * bold/italic pattern matched *there*. That broke `**bold**` in two ways:
 * the first `*` of the pair was consumed as a literal, so the remaining
 * `*text*` was re-interpreted as italic and then swallowed everything up to
 * the next `*` in the paragraph — which produced the giant accidental
 * italics and the "giảm nhẹ khoảm 0.52%" run-ons.
 */
function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;

  const pushText = (raw: string) => {
    if (!raw) return;
    nodes.push(<Fragment key={`t-${key++}`}>{raw}</Fragment>);
  };

  while (cursor < text.length) {
    const rest = text.slice(cursor);

    // Inline code: `...` (no nested backticks).
    const codeMatch = /^`([^`\n]+)`/.exec(rest);
    if (codeMatch) {
      nodes.push(
        <code
          key={`c-${key++}`}
          className="rounded bg-muted px-1 py-0.5 font-mono text-[12.5px] text-foreground"
        >
          {codeMatch[1]}
        </code>,
      );
      cursor += codeMatch[0].length;
      continue;
    }

    // Bold: **...** — checked BEFORE italic so `**x**` never degrades to `*x*`.
    const boldMatch = /^\*\*([^*\n]+)\*\*/.exec(rest);
    if (boldMatch) {
      nodes.push(
        <strong key={`b-${key++}`} className="font-semibold">
          {boldMatch[1]}
        </strong>,
      );
      cursor += boldMatch[0].length;
      continue;
    }

    // Italic: *...* — the content must not start or end with whitespace, so a
    // stray "*" (a multiplication sign, an unpaired asterisk) is not mistaken
    // for emphasis and is shown literally instead.
    const italicMatch = /^\*([^*\s](?:[^*\n]*[^*\s])?)\*/.exec(rest);
    if (italicMatch) {
      nodes.push(
        <em key={`i-${key++}`} className="italic">
          {italicMatch[1]}
        </em>,
      );
      cursor += italicMatch[0].length;
      continue;
    }

    // No emphasis marker at this position: copy one character verbatim.
    pushText(rest[0]);
    cursor += 1;
  }

  return nodes;
}

function renderBlock(block: Block, idx: number): ReactNode {
  switch (block.kind) {
    case "heading": {
      const safe = escapeHtml(block.text);
      const className =
        block.level === 1
          ? "text-base font-semibold text-foreground"
          : block.level === 2
            ? "text-sm font-semibold text-foreground"
            : "text-[13px] font-semibold text-foreground";
      return (
        <div key={idx} className={className}>
          {renderInline(safe)}
        </div>
      );
    }
    case "code":
      return (
        <pre
          key={idx}
          className="overflow-x-auto rounded-md bg-muted px-3 py-2 font-mono text-[12.5px] leading-relaxed text-foreground"
        >
          <code>{escapeHtml(block.content)}</code>
        </pre>
      );
    case "quote":
      return (
        <blockquote
          key={idx}
          className="border-l-2 border-muted-foreground/40 pl-3 text-muted-foreground"
        >
          {renderInline(escapeHtml(block.text))}
        </blockquote>
      );
    case "hr":
      return <hr key={idx} className="my-2 border-border" />;
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      const cls = block.ordered
        ? "list-decimal space-y-1.5 pl-5"
        : "list-disc space-y-1.5 pl-5";
      return (
        <Tag
          key={idx}
          className={cls}
          start={block.ordered ? block.start : undefined}
        >
          {block.items.map((item, j) => (
            <li key={j}>
              <div>{renderInline(escapeHtml(item.text))}</div>
              {item.children.map((child, k) => (
                <div key={k} className="mt-1">
                  {renderBlock(child, k)}
                </div>
              ))}
            </li>
          ))}
        </Tag>
      );
    }
    case "paragraph":
    default:
      return (
        <p key={idx} className="leading-relaxed">
          {renderInline(escapeHtml(block.text))}
        </p>
      );
  }
}

export function Markdown({ source }: { source: string }) {
  // Hard-cap rendering input. The chat pipeline already limits this, but a
  // pathological LLM reply should not be able to block the main thread.
  const safeSource = source.length > 20_000 ? source.slice(0, 20_000) + "\n…" : source;
  const blocks = parseMarkdown(safeSource);
  return (
    <div className="space-y-2 [&_p]:m-0 [&_ul]:m-0 [&_ol]:m-0">
      {blocks.map((block, idx) => renderBlock(block, idx))}
    </div>
  );
}
