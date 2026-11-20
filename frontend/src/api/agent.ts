import { api, ApiEnvelope } from "@/api/client";
import { AgentChatResponse, ChatSession, StoredTurn } from "@/types/agent";

export async function sendChat(sessionId: string, message: string, symbol?: string) {
  const { data } = await api.post<ApiEnvelope<AgentChatResponse>>("/agent/chat", {
    session_id: sessionId,
    message,
    symbol,
  });
  return data.data;
}

export async function fetchChatHistory(sessionId: string) {
  const { data } = await api.get<ApiEnvelope<StoredTurn[]>>(`/agent/history/${sessionId}`);
  return data.data;
}

/**
 * Every past chat session, newest activity first.
 *
 * WHY: the chat page needs a "past chats" list so a conversation survives
 * closing the tab. The backend already stores every turn in MySQL.
 */
export async function fetchChatSessions(): Promise<ChatSession[]> {
  const { data } = await api.get<ApiEnvelope<ChatSession[]>>("/agent/sessions");
  return data.data;
}

/** Delete a whole chat session. Returns the number of turns removed. */
export async function deleteChatSession(sessionId: string): Promise<number> {
  const { data } = await api.delete<ApiEnvelope<{ deleted: number }>>(
    `/agent/sessions/${sessionId}`,
  );
  return data.data.deleted;
}

/** Delete a single turn from a chat session. */
export async function deleteChatMessage(messageId: number): Promise<number> {
  const { data } = await api.delete<ApiEnvelope<{ deleted: number }>>(
    `/agent/messages/${messageId}`,
  );
  return data.data.deleted;
}

export async function fetchDashboard(symbol: string, start?: string) {
  const { data } = await api.get<ApiEnvelope<Record<string, unknown>>>(
    `/dashboard/${symbol}`,
    { params: start ? { start } : {} },
  );
  return data.data;
}

export async function fetchSystemStatus() {
  const { data } = await api.get<ApiEnvelope<Record<string, unknown>>>("/system/status");
  return data.data;
}

export async function runPipeline(symbol: string, interval: string) {
  const { data } = await api.post<{ status: string; errors: string[] }>(
    "/pipeline/run",
    { symbols: [symbol], interval, lookback_days: 120 },
    { timeout: 240000 },
  );
  if (data.status !== "success") {
    throw new Error(data.errors?.[0] || `Pipeline ${data.status}`);
  }
  return data;
}
