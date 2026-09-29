export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-down/40 bg-down/10 p-4 text-sm text-down">
      {message}
    </div>
  );
}
