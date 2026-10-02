import { Loader2 } from "lucide-react";

export function Loading({ label = "Dang tai du lieu" }: { label?: string }) {
  return (
    <div className="flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
      <Loader2 size={14} className="animate-spin" />
      <span>{label}</span>
    </div>
  );
}