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
 *   numbered lists, and blockquotes)
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

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; lang: string | null; content: string }
  | { kind: "quote"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] };

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

    // Bullet list: - or * at column 0
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s+/, ""));
        i += 1;
      }
      blocks.push({ kind: "list", ordered: false, items });
      continue;
    }

    // Numbered list: 1. 2. ...
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ""));
        i += 1;
      }
      blocks.push({ kind: "list", ordered: true, items });
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
      !/^[-*]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i])
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: buf.join(" ") });
  }

  return blocks;
}

function renderInline(text: string): ReactNode[] {
  // Walk left-to-right. Order matters: code first (so * inside code stays),
  // then bold (**), then italic (*), then plain text.
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
      pushText(text.slice(cursor, cursor + codeMatch[0].length).slice(0, 0));
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

    // Bold: **...** (must have a closing pair).
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

    // Italic: *...* (single asterisk). Guard against a stray "*" with no
    // closing partner, otherwise we'd silently swallow text.
    const italicMatch = /^\*([^*\n]+)\*/.exec(rest);
    if (italicMatch) {
      nodes.push(
        <em key={`i-${key++}`} className="italic">
          {italicMatch[1]}
        </em>,
      );
      cursor += italicMatch[0].length;
      continue;
    }

    // Plain text until the next interesting character.
    const nextSpecial = rest.search(/[`*]/);
    if (nextSpecial === -1) {
      pushText(rest);
      break;
    }
    pushText(rest.slice(0, nextSpecial));
    // Emit the unmatched special char as a literal so the user can see it
    // instead of losing data silently.
    pushText(rest[nextSpecial]);
    cursor += nextSpecial + 1;
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
    case "list": {
      const Tag = block.ordered ? "ol" : "ul";
      const cls = block.ordered
        ? "list-decimal pl-5 space-y-1"
        : "list-disc pl-5 space-y-1";
      return (
        <Tag key={idx} className={cls}>
          {block.items.map((item, j) => (
            <li key={j}>{renderInline(escapeHtml(item))}</li>
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
