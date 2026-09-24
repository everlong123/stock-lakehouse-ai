export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}
