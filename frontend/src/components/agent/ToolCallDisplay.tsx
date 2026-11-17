import { ChevronDown, ChevronUp, Wrench, XCircle } from "lucide-react";
import { useState } from "react";
import { ToolCallTrace } from "@/types/agent";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function ToolCallDisplay({ tools }: { tools: ToolCallTrace[] }) {
  if (!tools.length) return null;
  return (
    <div className="mt-2 flex flex-col gap-2">
      {tools.map((tool, index) => (
        <ToolItem key={`${tool.tool_name}-${index}`} tool={tool} />
      ))}
    </div>
  );
}

function ToolItem({ tool }: { tool: ToolCallTrace }) {
  const [open, setOpen] = useState(false);
  const failed = Boolean(tool.error);

  return (
    <div
      className={cn(
        "overflow-hidden rounded border bg-surface",
        failed ? "border-negative/30" : "border-hairline",
      )}
    >
      <button
        onClick={() => setOpen(!open)}
        className="flex min-h-9 w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-2"
      >
        <span
          className={cn(
            "flex h-5 w-5 items-center justify-center rounded text-muted",
            failed ? "text-negative" : "text-primary",
          )}
        >
          {failed ? <XCircle size={11} /> : <Wrench size={11} />}
        </span>
        <span className="font-mono text-small font-semibold text-ink">{tool.tool_name}</span>
        <Badge variant={failed ? "negative" : "primary"}>{failed ? "failed" : "ok"}</Badge>
        <span className="ml-auto text-muted">
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>
      {open ? (
        <div className="border-t border-hairline bg-surface-2 px-3 py-3 text-small">
          <div className="mb-3">
            <span className="font-mono text-label uppercase text-muted">
              Arguments
            </span>
            <pre className="mt-1 overflow-auto rounded bg-surface p-2 font-mono text-label text-ink">
              {JSON.stringify(tool.tool_arguments, null, 2)}
            </pre>
          </div>
          <div>
            <span className="font-mono text-label uppercase text-muted">
              Result
            </span>
            <pre className="mt-1 max-h-40 overflow-auto rounded bg-surface p-2 font-mono text-label text-ink">
              {JSON.stringify(tool.tool_result, null, 2).slice(0, 600)}
              {JSON.stringify(tool.tool_result).length > 600 ? "..." : null}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}
