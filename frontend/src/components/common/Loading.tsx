export function Loading({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
      <div className="mr-3 h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      {label}
    </div>
  );
}
