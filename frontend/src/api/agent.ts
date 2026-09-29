import { api, ApiEnvelope } from "@/api/client";
import { AgentChatResponse } from "@/types/agent";

export async function sendChat(sessionId: string, message: string, symbol?: string) {
  const { data } = await api.post<ApiEnvelope<AgentChatResponse>>("/agent/chat", {
    session_id: sessionId,
    message,
    symbol,
  });
  return data.data;
}

export async function fetchChatHistory(sessionId: string) {
  const { data } = await api.get<ApiEnvelope<Record<string, unknown>[]>>(`/agent/history/${sessionId}`);
  return data.data;
}

export async function fetchDashboard(symbol: string) {
  const { data } = await api.get<ApiEnvelope<Record<string, unknown>>>(`/dashboard/${symbol}`);
  return data.data;
}

export async function fetchSystemStatus() {
  const { data } = await api.get<ApiEnvelope<Record<string, unknown>>>("/system/status");
  return data.data;
}

export async function runPipeline(symbol: string, interval: string) {
  const { data } = await api.post<ApiEnvelope<Record<string, unknown>>>("/pipeline/run", { symbol, interval });
  return data.data;
}
