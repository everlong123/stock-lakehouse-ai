export interface ToolCallTrace {
  tool_name: string;
  tool_arguments: Record<string, unknown>;
  tool_result: unknown;
  error?: string | null;
}

export interface AgentChatResponse {
  session_id: string;
  assistant_message: string;
  tools: ToolCallTrace[];
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  tools?: ToolCallTrace[];
}
