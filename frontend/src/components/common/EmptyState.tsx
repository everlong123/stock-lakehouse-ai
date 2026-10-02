export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center rounded-md border border-dashed border-border bg-muted/40 px-6 py-12 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}