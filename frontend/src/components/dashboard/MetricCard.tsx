import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  delta?: number | null;
  hint?: string;
}

export function MetricCard({ label, value, delta, hint }: MetricCardProps) {
  const [flashing, setFlashing] = useState(false);
  const prevValue = useRef<string>(value);

  const trend =
    delta === undefined || delta === null
      ? "neutral"
      : delta > 0
        ? "up"
        : delta < 0
          ? "down"
          : "neutral";

  // Flash animation when value changes
  useEffect(() => {
    if (prevValue.current !== value) {
      setFlashing(true);
      const t = setTimeout(() => setFlashing(false), 800);
      prevValue.current = value;
      return () => clearTimeout(t);
    }
  }, [value]);

  const trendColor = {
    up:      { color: "hsl(152 58% 38%)", bg: "hsl(152 58% 38% / 0.1)", border: "hsl(152 58% 38% / 0.2)" },
    down:    { color: "hsl(4 80% 52%)",  bg: "hsl(4 80% 52% / 0.1)",   border: "hsl(4 80% 52% / 0.2)"  },
    neutral: { color: "hsl(220 12% 50%)", bg: "hsl(210 20% 94%)",        border: "hsl(210 18% 88%)"      },
  }[trend];

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-2xl border bg-white p-4",
        "transition-all duration-300",
        "hover:shadow-md hover:-translate-y-0.5",
        flashing ? "scale-[0.98]" : "scale-100",
      )}
      style={{
        borderColor: "hsl(210 18% 90% / 0.7)",
        boxShadow: "0 1px 3px hsl(0 0% 0% / 0.04), 0 1px 2px hsl(0 0% 0% / 0.02)",
      }}
    >
      {/* Subtle top accent line */}
      <div
        className="absolute inset-x-0 top-0 h-[2px]"
        style={{
          background: trend === "up"
            ? "linear-gradient(90deg, hsl(152 58% 38%) 0%, hsl(152 58% 38% / 0.3) 100%)"
            : trend === "down"
              ? "linear-gradient(90deg, hsl(4 80% 52%) 0%, hsl(4 80% 52% / 0.3) 100%)"
              : "linear-gradient(90deg, hsl(165 52% 28%) 0%, hsl(165 52% 28% / 0.2) 100%)",
        }}
      />

      {/* Label */}
      <div
        className="mb-3 font-mono text-[10px] uppercase tracking-widest"
        style={{ color: "hsl(220 12% 50%)" }}
      >
        {label}
      </div>

      {/* Value */}
      <div
        className={cn(
          "font-mono font-semibold leading-none transition-all duration-500",
          flashing ? "opacity-70" : "opacity-100",
        )}
        style={{ fontSize: 24, color: "hsl(220 25% 10%)" }}
      >
        {value}
      </div>

      {/* Delta + hint row */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {/* Delta badge */}
        <div
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[11px] font-semibold"
          style={{
            color: trendColor.color,
            background: trendColor.bg,
            border: `1px solid ${trendColor.border}`,
          }}
        >
          {trend === "up" && <ArrowUp size={10} />}
          {trend === "down" && <ArrowDown size={10} />}
          {trend === "neutral" && <Minus size={10} />}
          {delta !== undefined && delta !== null
            ? `${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(2)}%`
            : "0.00%"}
        </div>

        {/* Hint */}
        {hint && (
          <div
            className="line-clamp-1 text-[10px] leading-relaxed"
            style={{ color: "hsl(220 12% 60%)" }}
          >
            {hint}
          </div>
        )}
      </div>
    </div>
  );
}
