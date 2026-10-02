import { ChevronDown, ChevronUp, Wrench, XCircle } from "lucide-react";
import { useState } from "react";
import { ToolCallTrace } from "@/types/agent";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function ToolCallDisplay({ tools }: { tools: ToolCallTrace[] }) {
  if (!tools.length) return null;
  return (
    <div className="ml-9 mt-1.5 flex flex-col gap-1.5">
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
        "overflow-hidden rounded-md border bg-card",
        failed ? "border-down/30" : "border-border",
      )}
    >
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40"
      >
        <span
          className={cn(
            "flex h-5 w-5 items-center justify-center rounded text-muted-foreground",
            failed ? "text-down" : "text-up",
          )}
        >
          {failed ? <XCircle size={11} /> : <Wrench size={11} />}
        </span>
        <span className="font-mono text-[12px] font-semibold">{tool.tool_name}</span>
        <Badge variant={failed ? "danger" : "success"}>{failed ? "failed" : "ok"}</Badge>
        <span className="ml-auto text-muted-foreground">
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>
      {open ? (
        <div className="border-t border-border bg-muted/30 px-3 py-2 text-[11px]">
          <div className="mb-1.5">
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Arguments
            </span>
            <pre className="mt-1 overflow-auto rounded bg-card p-2 font-mono text-[11px]">
              {JSON.stringify(tool.tool_arguments, null, 2)}
            </pre>
          </div>
          <div>
            <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              Result
            </span>
            <pre className="mt-1 max-h-40 overflow-auto rounded bg-card p-2 font-mono text-[11px]">
              {JSON.stringify(tool.tool_result, null, 2).slice(0, 600)}
              {JSON.stringify(tool.tool_result).length > 600 ? "..." : null}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}