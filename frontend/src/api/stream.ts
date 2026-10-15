import { api, ApiEnvelope } from "@/api/client";

export interface StreamBar {
  symbol: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
  received_at: string;
}

export interface StreamStats {
  symbols_tracked: number;
  total_recorded: number;
  started_at: string;
  uptime_seconds: number;
}

export async function fetchStreamLatest(symbol?: string) {
  const { data } = await api.get<ApiEnvelope<{ bar: StreamBar | null; symbol?: string } | { bars: Record<string, StreamBar>; stats: StreamStats }>>(
    "/stream/latest",
    { params: symbol ? { symbol } : {} },
  );
  return data.data;
}

export async function fetchStreamHistory(symbol: string, limit = 60) {
  const { data } = await api.get<ApiEnvelope<{ symbol: string; bars: StreamBar[]; count: number }>>(
    "/stream/history",
    { params: { symbol, limit } },
  );
  return data.data;
}

export async function fetchStreamStats() {
  const { data } = await api.get<ApiEnvelope<StreamStats>>("/stream/stats");
  return data.data;
}

export async function ingestStreamBars(payload: { symbol: string; bars: StreamBar[] }) {
  const { data } = await api.post<ApiEnvelope<{ symbol: string; accepted: number }>>(
    "/stream/ingest",
    payload,
  );
  return data.data;
}

// ── Server-Sent Events ────────────────────────────────────────────────────────
// The backend pushes one ``bar`` event per new OHLCV bar recorded in the
// in-memory cache. We expose a tiny client so React components can use it
// without touching EventSource directly.

export type StreamEventType = "bar" | "hello" | "ping";

export interface StreamEvent<T = StreamBar | { status?: string; ts?: string }> {
  type: StreamEventType;
  data: T;
}

export interface StreamSubscription {
  /** Stop receiving events and close the underlying EventSource. */
  close(): void;
}

export function subscribeStream(
  onEvent: (event: StreamEvent) => void,
  options: { symbol?: string; onError?: (err: Event) => void } = {},
): StreamSubscription {
  const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  const url = options.symbol
    ? `${base}/stream/events?symbol=${encodeURIComponent(options.symbol)}`
    : `${base}/stream/events`;

  const es = new EventSource(url, { withCredentials: false });

  const handle = (type: StreamEventType) => (message: MessageEvent) => {
    try {
      const data = JSON.parse(message.data);
      onEvent({ type, data });
    } catch {
      // Malformed payload — ignore, don't kill the subscription.
    }
  };

  es.addEventListener("bar", handle("bar"));
  es.addEventListener("hello", handle("hello"));
  es.addEventListener("ping", handle("ping"));

  if (options.onError) {
    es.addEventListener("error", options.onError);
  }

  return {
    close: () => {
      es.removeEventListener("bar", handle("bar"));
      es.removeEventListener("hello", handle("hello"));
      es.removeEventListener("ping", handle("ping"));
      es.close();
    },
  };
}