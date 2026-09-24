export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${formatNumber(value, 2)}`;
}

export function shortDate(value: string): string {
  return value.replace("T", " ").slice(0, 16);
}

export function changeClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-muted-foreground";
  if (value > 0) return "text-up";
  if (value < 0) return "text-down";
  return "text-muted-foreground";
}
