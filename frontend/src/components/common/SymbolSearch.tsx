import { useEffect, useMemo, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface SymbolSearchProps {
  /** The symbol currently selected. */
  value: string;
  /** Every symbol the lakehouse actually holds. */
  symbols: string[];
  onSelect: (symbol: string) => void;
  placeholder?: string;
  className?: string;
}

/**
 * The symbol search box in the top bar.
 *
 * WHY A SEARCH BOX AND NOT A `<select>`
 * -------------------------------------
 * The lakehouse holds more than a thousand tickers. A native `<select>`
 * with a thousand `<option>`s is unusable on Windows: the dropdown is a
 * flat, unsearchable list and opening it costs a visible stall. Yahoo
 * Finance solves this with a combobox - a text field that FILTERS the
 * universe as you type and shows the matches in a dropdown.
 *
 * So this is the same idea, hand-built from a text input and a list, and
 * it costs no new dependency.
 *
 * WHY THE MATCHING IS A SUBSTRING, NOT A FUZZY SCORE: the reader types
 * "vc" and wants VCB, VCI, VHM. A substring test on a lowercased symbol
 * answers that in one pass over the list, and a fuzzy score would rank a
 * weird match above the obvious one.
 *
 * WHY THE LIST IS NOT VIRTUALISED: the filtered list is at most a few
 * dozen rows - the whole universe is only rendered when the query is
 * empty, and then it is capped at 40. Rendering 1 000 rows of a text
 * label is cheap compared to the win of instant filtering.
 *
 * WHY NOTHING IS INVENTED: the list comes from `GET /stocks/symbols`,
 * which enumerates the symbols that have parquet in Bronze. A symbol
 * that is not in the lakehouse cannot be typed, so the picker can never
 * offer a ticker the pages cannot load.
 */
export function SymbolSearch({
  value,
  symbols,
  onSelect,
  placeholder = "Mã chứng khoán",
  className,
}: SymbolSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // The matches, in the lakehouse's own order, capped so the empty query
  // does not render the whole universe.
  const matches = useMemo(() => {
    const needle = query.trim().toUpperCase();
    const list = needle
      ? symbols.filter((symbol) => symbol.includes(needle))
      : symbols;
    return list.slice(0, 40);
  }, [query, symbols]);

  // Close the dropdown when the pointer lands outside the widget.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  // The highlighted row follows the filtered list.
  useEffect(() => setCursor(0), [query]);

  const commit = (symbol: string) => {
    onSelect(symbol);
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  };

  return (
    <div ref={rootRef} className={cn("relative w-full", className)}>
      <label className="flex h-9 items-center gap-2 rounded border border-hairline bg-surface px-3 transition-colors focus-within:border-primary focus-within:shadow-sm">
        <Search size={14} className="shrink-0 text-muted" aria-hidden="true" />
        <span className="sr-only">{placeholder}</span>
        <input
          ref={inputRef}
          value={open ? query : ""}
          placeholder={value ? value : placeholder}
          onChange={(event) => {
            setQuery(event.target.value.toUpperCase());
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setOpen(true);
              setCursor((c) => Math.min(c + 1, matches.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setCursor((c) => Math.max(c - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              const pick = matches[cursor];
              if (pick) commit(pick);
            } else if (event.key === "Escape") {
              setOpen(false);
              setQuery("");
            }
          }}
          className="min-w-0 flex-1 bg-transparent font-mono text-small font-semibold text-ink outline-none placeholder:font-sans placeholder:font-normal placeholder:text-muted"
          autoComplete="off"
          spellCheck={false}
        />
        {open && query ? (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              inputRef.current?.focus();
            }}
            aria-label="Xoá tìm kiếm"
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted hover:text-ink"
          >
            <X size={12} />
          </button>
        ) : null}
      </label>

      {open ? (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] z-50 max-h-80 overflow-y-auto rounded border border-hairline bg-surface shadow-popover">
          {matches.length === 0 ? (
            <p className="px-3 py-3 text-small text-muted">
              Không có mã nào khớp trong lakehouse.
            </p>
          ) : (
            <ul>
              {matches.map((symbol, index) => {
                const active = symbol === value;
                return (
                  <li key={symbol}>
                    <button
                      type="button"
                      onMouseEnter={() => setCursor(index)}
                      onClick={() => commit(symbol)}
                      className={cn(
                        "flex min-h-9 w-full items-center justify-between gap-3 px-3 text-left transition-colors",
                        index === cursor ? "bg-primary/10" : "hover:bg-surface-2",
                      )}
                    >
                      <span
                        className={cn(
                          "font-mono text-small font-semibold",
                          active ? "text-primary" : "text-ink",
                        )}
                      >
                        {symbol}
                      </span>
                      {active ? (
                        <span className="font-mono text-label uppercase text-primary">
                          đang xem
                        </span>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
