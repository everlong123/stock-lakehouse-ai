import { Badge } from "@/components/ui/badge";
import { ToolCallTrace } from "@/types/agent";

export function ToolCallDisplay({ tools }: { tools: ToolCallTrace[] }) {
  if (!tools.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {tools.map((tool, index) => (
        <Badge key={`${tool.tool_name}-${index}`}>
          Tool called: {tool.tool_name}
          {tool.error ? " (failed)" : ""}
        </Badge>
      ))}
    </div>
  );
}
