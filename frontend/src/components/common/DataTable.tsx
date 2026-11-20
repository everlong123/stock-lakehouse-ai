import { ArrowDown, ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";

export type SortDirection = "asc" | "desc";

export interface SortState<K extends string> {
  key: K;
  direction: SortDirection;
}

export interface Column<Row> {
  key: string;
  label: string;
  /** The value to sort by. Falls back to the raw cell when omitted. */
  sortValue?: (row: Row) => number | string | null;
  /** Right-aligned numeric columns read faster when their digits line up. */
  align?: "left" | "right";
  className?: string;
  render: (row: Row) => React.ReactNode;
}

/**
 * A sortable data table.
 *
 * WHY SORTING IS BUILT IN RATHER THAN LEFT TO THE READER
 * --------------------------------------------------------
 * The session table is the one place in this app where the reader has
 * more rows than they can read, and the question they bring to it is
 * almost never "row 143" — it is "the biggest up day", "the heaviest
 * volume", "the highest close". Those questions are sorting questions,
 * and a table that cannot be sorted makes the reader scan every row to
 * answer one.
 *
 * WHY THE SORT STATE LIVES IN THE PAGE AND NOT HERE: the table only
 * renders. The page owns which column is sorted, because the page also
 * owns the CSV export, and an export that does not match what is on
 * screen is a lie.
 *
 * WHY THE ARROW IS IN THE HEADER AND NOT A SEPARATE CONTROL: the header
 * is already the affordance for "this column has a name", so it is also
 * the affordance for "this column can be ordered". A separate control
 * would double the number of things to look at.
 */
export function DataTable<Row extends object>({
  columns,
  rows,
  sort,
  onSortChange,
  rowKey,
  emptyMessage,
  maxHeight,
}: {
  columns: Column<Row>[];
  rows: Row[];
  sort: SortState<string>;
  onSortChange: (next: SortState<string>) => void;
  rowKey: (row: Row, index: number) => string;
  emptyMessage: string;
  maxHeight?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-auto rounded border border-hairline bg-surface shadow-sm",
        maxHeight,
      )}
    >
      <table className="table">
        <thead className="sticky top-0 z-10">
          <tr>
            {columns.map((column) => {
              const active = sort.key === column.key;
              const Arrow = sort.direction === "asc" ? ArrowUp : ArrowDown;
              return (
                <th
                  key={column.key}
                  className={cn(
                    column.align === "right" && "text-right",
                    column.className,
                  )}
                  aria-sort={
                    active
                      ? sort.direction === "asc"
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button
                    type="button"
                    onClick={() =>
                      onSortChange({
                        key: column.key,
                        direction:
                          active && sort.direction === "desc" ? "asc" : "desc",
                      })
                    }
                    className={cn(
                      "inline-flex min-h-8 items-center gap-1 transition-colors",
                      active ? "text-ink" : "hover:text-ink",
                    )}
                  >
                    {column.label}
                    <Arrow
                      size={11}
                      className={cn(
                        "shrink-0",
                        active ? "text-primary" : "text-hairline",
                      )}
                      aria-hidden="true"
                    />
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-10 text-center text-small text-muted"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              /*
                WHY EACH ROW CARRIES `content-visibility`: the session
                table can hold 2 500 rows. Without it the browser lays
                out and paints every one of them, even the 2 300 that
                are off screen — which is what makes a long table scroll
                in stutters. The browser skips the off-screen rows and
                keeps the scrollbar honest with an intrinsic size.
              */
              <tr key={rowKey(row, index)} className="cv-auto">
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      column.align === "right" && "text-right",
                      column.className,
                    )}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Sort a list of rows by one column.
 *
 * WHY THE COMPARATOR IS WRITTEN OUT RATHER THAN DELEGATED TO A HELPER:
 * the columns hold mixed types — numbers for prices, strings for dates —
 * and a generic comparator would need a type discriminator. Writing it
 * here keeps the two rules visible: numbers compare numerically, and
 * anything unusable sorts LAST in both directions, so a row with a null
 * price never floats to the top pretending to be the biggest.
 */
export function sortRows<Row extends object>(
  rows: Row[],
  columns: Column<Row>[],
  sort: SortState<string>,
): Row[] {
  const column = columns.find((c) => c.key === sort.key);
  if (!column) return rows;

  const valueOf = (row: Row): number | string | null => {
    if (column.sortValue) return column.sortValue(row);
    const raw = (row as Record<string, unknown>)[column.key];
    if (typeof raw === "number" || typeof raw === "string") return raw;
    return null;
  };

  const direction = sort.direction === "asc" ? 1 : -1;

  return [...rows].sort((a, b) => {
    const av = valueOf(a);
    const bv = valueOf(b);
    const aMissing = av === null || av === undefined;
    const bMissing = bv === null || bv === undefined;
    // Missing values always sink to the bottom.
    if (aMissing && bMissing) return 0;
    if (aMissing) return 1;
    if (bMissing) return -1;

    if (typeof av === "number" && typeof bv === "number") {
      return (av - bv) * direction;
    }
    return String(av).localeCompare(String(bv)) * direction;
  });
}
