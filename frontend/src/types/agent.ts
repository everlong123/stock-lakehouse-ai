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
  suggested_questions?: string[];
  tool_count?: number;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  tools?: ToolCallTrace[];
  suggested_questions?: string[];
  tool_count?: number;
  /** The row id in MySQL. Present only for turns loaded from the server. */
  id?: number;
}

/** One stored turn of a session, as the backend returns it. */
export interface StoredTurn {
  id: number;
  session_id: string;
  user_message: string;
  assistant_message: string | null;
  tool_name: string | null;
  tool_arguments: string | null;
  tool_result: string | null;
  created_at: string | null;
}

/** One entry of the "past chats" list. */
export interface ChatSession {
  session_id: string;
  /** The first user message, truncated. A real label, not "Chat 1". */
  title: string;
  started_at: string | null;
  last_active: string | null;
  message_count: number;
}
