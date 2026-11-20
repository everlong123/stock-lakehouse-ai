import { useMemo } from "react";
import { cn } from "@/lib/utils";

export type SparklineTone = "up" | "down" | "brand" | "muted" | "auto";

interface SparklineProps {
  /** The series, oldest first. Non-finite values are skipped. */
  values: number[];
  width?: number;
  height?: number;
  tone?: SparklineTone;
  className?: string;
  /** Announced to a screen reader; omit to keep the chart decorative. */
  label?: string;
}

/**
 * A tiny inline price line.
 *
 * WHY RAW SVG AND NOT RECHARTS: a sparkline is a hundred pixels wide and
 * carries one series. Recharts costs 407 kB raw / 110 kB gzipped, and it
 * mounts a whole chart runtime — a responsive container, an axis engine and
 * an animation scheduler — to draw a single polyline. A watchlist with
 * twelve rows would mount twelve of those.
 *
 * The hand-drawn version is ~30 lines, has no dependency, and paints on the
 * first frame. It is also smaller on the wire than the recharts chunk, so
 * it can live in the MAIN bundle instead of being lazily loaded — which
 * matters, because the watchlist is above the fold.
 *
 * WHY THE LINE HAS A SOFT AREA UNDER IT: at this size a fill is a few
 * pixels of colour between the line and the baseline, and a FLAT tint of
 * the line's own colour gives the shape a body. It is one colour at low
 * opacity — not a gradient sweep — so it reads as a shape, not as an
 * effect.
 *
 * WHY A FLAT LINE IS DRAWN, NOT NOTHING: a symbol with one stored close
 * has no shape to draw, but it is still a real symbol. A horizontal line
 * says "one point" honestly; an empty box says "no data", which is a
 * different claim.
 */
export function Sparkline({
  values,
  width = 72,
  height = 24,
  tone = "auto",
  className,
  label,
}: SparklineProps) {
  const geometry = useMemo(() => {
    const points = values.filter((v) => Number.isFinite(v));
    if (points.length < 2) return null;

    const min = Math.min(...points);
    const max = Math.max(...points);
    const span = max - min;
    // A flat series has no shape to draw, so the line is pinned to the
    // middle rather than stretched across a zero-height band.
    const flat = span === 0;
    const stepX = width / (points.length - 1);
    const pad = 3;
    const usable = height - pad * 2;

    const coords = points.map((value, index) => {
      const x = index * stepX;
      const y = flat
        ? height / 2
        : pad + (1 - (value - min) / span) * usable;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });

    const first = points[0];
    const last = points[points.length - 1];
    const direction = last > first ? "up" : last < first ? "down" : "muted";

    return {
      path: `M${coords.join(" L")}`,
      area: `M0,${height} L${coords.join(" L")} L${width},${height} Z`,
      direction,
    };
  }, [values, width, height]);

  const stroke =
    tone === "auto"
      ? geometry?.direction === "up"
        ? "hsl(var(--up))"
        : geometry?.direction === "down"
          ? "hsl(var(--negative))"
          : "hsl(var(--muted))"
      : tone === "up"
        ? "hsl(var(--up))"
        : tone === "down"
          ? "hsl(var(--negative))"
          : tone === "brand"
            ? "hsl(var(--primary))"
            : "hsl(var(--muted))";

  if (!geometry) {
    return (
      <svg
        width={width}
        height={height}
        className={cn("shrink-0", className)}
        role={label ? "img" : "presentation"}
        aria-label={label}
        aria-hidden={label ? undefined : true}
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="hsl(var(--hairline))"
          strokeWidth={1}
        />
      </svg>
    );
  }

  return (
    <svg
      width={width}
      height={height}
      className={cn("shrink-0", className)}
      role={label ? "img" : "presentation"}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {/* The body of the shape. A flat tint of the line's own colour. */}
      <path d={geometry.area} fill={stroke} fillOpacity={0.1} />
      <path
        d={geometry.path}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        /*
          WHY THE LINE DRAWS ITSELF IN: a price line that appears fully
          drawn gives the reader no sense that anything just loaded. A
          700ms left-to-right draw says "this series arrived" without
          moving a single number. `pathLength="1"` normalises the dash
          maths so the stroke length never has to be measured in JS.
        */
        pathLength={1}
        className="spark-draw"
        strokeDasharray={1}
        strokeDashoffset={1}
      />
    </svg>
  );
}
