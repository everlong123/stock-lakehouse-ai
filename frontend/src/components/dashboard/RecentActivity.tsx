export function RecentActivity({
  pipeline,
  model,
  backtest,
}: {
  pipeline?: Record<string, unknown> | null;
  model?: Record<string, unknown> | null;
  backtest?: Record<string, unknown> | null;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-sm font-semibold">Recent activity</div>
      <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
        <li>Pipeline: {pipeline ? String(pipeline.status ?? "available") : "No pipeline run yet"}</li>
        <li>Latest model: {model ? String(model.model_name) : "No trained model found. Please train the model first."}</li>
        <li>Latest backtest: {backtest ? String(backtest.strategy) : "No backtest yet"}</li>
      </ul>
    </div>
  );
}
