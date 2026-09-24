import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
  timeout: 180000,
});

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  message: string | null;
}

export function isBackendOffline(error: unknown): boolean {
  return axios.isAxiosError(error) && !error.response;
}

export function errorMessage(error: unknown, fallback: string): string {
  if (isBackendOffline(error)) return "Cannot connect to backend API.";
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as { message?: string } | undefined;
    return payload?.message || error.message || fallback;
  }
  return fallback;
}
