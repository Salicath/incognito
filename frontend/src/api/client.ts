const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  getStatus: () => request<{ initialized: boolean }>("/auth/status"),
  unlock: (password: string) =>
    request("/auth/unlock", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  lock: () => request("/auth/lock", { method: "POST" }),
  setup: (data: { password: string; profile: unknown; smtp?: unknown }) =>
    request("/setup", { method: "POST", body: JSON.stringify(data) }),
  getProfile: () => request<Record<string, unknown>>("/profile"),
  getBrokers: () => request<Array<Record<string, unknown>>>("/brokers"),
  getBroker: (id: string) => request<Record<string, unknown>>(`/brokers/${id}`),
  getRequests: (status?: string) =>
    request<Array<Record<string, unknown>>>(
      `/requests${status ? `?status=${status}` : ""}`
    ),
  getRequest: (id: string) => request<Record<string, unknown>>(`/requests/${id}`),
  getRequestEvents: (id: string) =>
    request<Array<Record<string, unknown>>>(`/requests/${id}/events`),
  createRequest: (brokerId: string, requestType: string) =>
    request("/requests", {
      method: "POST",
      body: JSON.stringify({ broker_id: brokerId, request_type: requestType }),
    }),
  transitionRequest: (id: string, action: string, details?: string) =>
    request(`/requests/${id}/transition`, {
      method: "POST",
      body: JSON.stringify({ action, details }),
    }),
  getStats: () => request<Record<string, number>>("/requests/stats"),
  startScan: () => request<{ status: string; hits: number; checked: number }>("/scan/start", { method: "POST" }),
  getScanResults: () => request<{ has_results: boolean; checked: number; hits: Array<{ broker_domain: string; broker_name: string; snippet: string; url: string }> }>("/scan/results"),
  getScanStatus: () => request<{ running: boolean }>("/scan/status"),
};
