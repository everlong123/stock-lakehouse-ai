import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  // The backend enforces its own deadline (AGENT_REQUEST_TIMEOUT_SECONDS,
  // currently 75s) and returns a 504 with an actionable message when a
  // request exceeds it. This client-side ceiling is deliberately a little
  // higher so the server's clearer message wins the race - if the server
  // answers at 76s we want the user's screen to show the server's
  // explanation, not this generic abort.
  timeout: 90000,
});

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  message: string | null;
}

export function isBackendOffline(error: unknown): boolean {
  return axios.isAxiosError(error) && !error.response;
}

export function isTimeout(error: unknown): boolean {
  return axios.isAxiosError(error) && error.code === "ECONNABORTED";
}

export function errorMessage(error: unknown, fallback: string): string {
  // A timeout is NOT an offline backend: the request reached the server but
  // the answer took too long. Reporting it as "cannot connect" sent users
  // hunting for a networking bug that did not exist.
  if (isTimeout(error)) {
    return "Yêu cầu mất quá lâu (>90s) nên đã bị hủy. Backend vẫn đang xử lý — thử lại hoặc rút gọn câu hỏi.";
  }
  if (isBackendOffline(error)) return "Cannot connect to backend API.";
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as { message?: string } | undefined;
    // Prefer the server's own message: a 504 from the agent service carries
    // a specific, actionable explanation that is more useful than the
    // generic axios text.
    return payload?.message || error.message || fallback;
  }
  return fallback;
}
