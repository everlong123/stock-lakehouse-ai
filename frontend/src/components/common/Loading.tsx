import { Loader2 } from "lucide-react";

export function Loading({ label = "Đang tải dữ liệu..." }: { label?: string }) {
  return (
    <div className="flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
      <Loader2 size={16} className="animate-spin text-brand-600" />
      {label}
    </div>
  );
}