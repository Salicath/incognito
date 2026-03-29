const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    let message = res.statusText;
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      message = body.detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join(", ");
    }
    throw new Error(message);
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
  startScan: () => request<{ status: string; total: number }>("/scan/start", { method: "POST" }),
  getScanResults: () => request<{ has_results: boolean; checked: number; hits: Array<{ broker_domain: string; broker_name: string; snippet: string; url: string }> }>("/scan/results"),
  getScanStatus: () => request<{ running: boolean; progress: number; total: number; error: string | null }>("/scan/status"),
  startAccountScan: (email?: string) =>
    request<{ status: string; email: string }>(`/scan/accounts/start${email ? `?email=${encodeURIComponent(email)}` : ""}`, { method: "POST" }),
  getAccountResults: () => request<{ has_results: boolean; email: string; checked: number; hits: Array<{ service: string; url: string }>; errors: string[] }>("/scan/accounts/results"),
  getAccountStatus: () => request<{ running: boolean; progress: number; total: number; error: string | null }>("/scan/accounts/status"),
  getHibpStatus: () => request<{ configured: boolean; key_preview?: string }>("/settings/hibp"),
  saveHibpKey: (apiKey: string) => request("/settings/hibp", { method: "POST", body: JSON.stringify({ api_key: apiKey }) }),
  deleteHibpKey: () => request("/settings/hibp", { method: "DELETE" }),
  startBreachCheck: (email?: string) =>
    request<{ status: string; email: string }>(`/scan/breaches/start${email ? `?email=${encodeURIComponent(email)}` : ""}`, { method: "POST" }),
  getBreachResults: () =>
    request<{ has_results: boolean; email: string; total_breaches: number; breaches: Array<{ name: string; title: string; domain: string; breach_date: string; pwn_count: number; data_classes: string[] }>; error: string | null }>("/scan/breaches/results"),
  getBreachStatus: () =>
    request<{ running: boolean; error: string | null }>("/scan/breaches/status"),
  blastCreate: (requestType: string, dryRun: boolean) =>
    request<{ dry_run: boolean; created: number; skipped: number; total_brokers: number; requests: Array<Record<string, string>> }>("/blast/create", {
      method: "POST",
      body: JSON.stringify({ request_type: requestType, dry_run: dryRun }),
    }),
  blastSendAll: () =>
    request<{ sent: number; failed: number; manual: number; total: number; results: Array<Record<string, string>> }>("/blast/send-all", { method: "POST" }),
  runFollowUp: () =>
    request<{ newly_overdue: number; follow_ups_sent: number; escalations_sent: number; errors: string[] }>("/blast/follow-up", { method: "POST" }),
  generateComplaint: (requestId: string) =>
    request<{
      complaint_text: string;
      dpa: { name: string; short_name: string; email: string | null; url: string; language: string } | null;
      broker: { name: string; domain: string; dpo_email: string; country: string };
      request_id: string;
    }>(`/blast/generate-complaint/${requestId}`, { method: "POST" }),
  getRescanReport: () =>
    request<{
      has_results: boolean;
      reappeared: Array<{ broker_domain: string; broker_name: string; snippet: string; url: string; previous_removal_date: string | null }>;
      new_exposures: Array<{ broker_domain: string; broker_name: string; snippet: string; url: string }>;
      total_checked: number;
      scan_date?: string;
    }>("/scan/rescan"),
  getScanHistory: () =>
    request<{
      results: Array<{ id: number; source: string; broker_id: string; found_data: unknown; scanned_at: string | null; actioned: boolean }>;
      total: number;
    }>("/scan/history"),
  getImapStatus: () => request<{ configured: boolean; host?: string; port?: number; username?: string; folder?: string; poll_interval_minutes?: number; starttls?: boolean }>("/settings/imap"),
  saveImap: (imap: { host: string; port: number; username: string; password: string; folder?: string; poll_interval_minutes?: number; starttls?: boolean }) =>
    request("/settings/imap", { method: "POST", body: JSON.stringify({ imap }) }),
  deleteImap: () => request("/settings/imap", { method: "DELETE" }),
  testImap: () => request<{ status: string; folders: string[] }>("/settings/imap/test", { method: "POST" }),
  getImapPollerStatus: () => request<{ enabled: boolean; last_check: string | null; matched_count: number; unmatched_count: number; poll_interval_minutes: number | null; last_error: string | null }>("/settings/imap/status"),
  getSmtpStatus: () => request<{ configured: boolean; host?: string; port?: number; username?: string }>("/settings/smtp"),
  saveSmtp: (smtp: { host: string; port: number; username: string; password: string }) =>
    request("/settings/smtp", { method: "POST", body: JSON.stringify({ smtp }) }),
  getAppInfo: () => request<{ broker_count: number; dpa_count?: number; locale_count?: number; data_dir: string; version: string; notifications?: boolean }>("/settings/info"),
  saveProfile: (profile: { full_name: string; emails: string[]; phones: string[]; date_of_birth?: string }) =>
    request("/settings/profile", { method: "POST", body: JSON.stringify({ profile }) }),
  testSmtp: () => request<{ status: string; message: string }>("/settings/test-smtp", { method: "POST" }),
  getAuditTrail: () =>
    request<{ generated_at: string; total_requests: number; trail: Array<Record<string, unknown>> }>("/requests/export/audit-trail"),
  getExposureReport: () =>
    request<{
      generated_at: string;
      score: number;
      grade: string;
      summary: { total_brokers_contacted: number; completed: number; in_progress: number; exposures_found: number };
      brokers: Array<{ broker_id: string; broker_name: string; status: string; sent_at: string | null; response_at: string | null }>;
      exposures: Array<{ source: string; broker_id: string; scanned_at: string | null; actioned: boolean }>;
    }>("/requests/report/exposure"),
  getNotificationStatus: () =>
    request<{ configured: boolean; url: string | null }>("/settings/notifications"),
  testNotification: () =>
    request<{ status: string }>("/settings/notifications/test", { method: "POST" }),
  exportBackup: (password: string) =>
    request<Record<string, unknown>>("/settings/backup/export", { method: "POST", body: JSON.stringify({ password }) }),
  importBackup: (data: Record<string, unknown>) =>
    request<{ status: string; message: string }>("/settings/backup/import", { method: "POST", body: JSON.stringify(data) }),
  importCsv: (csv: string) =>
    request<{ imported: number; skipped: number; errors: string[] }>("/settings/import-csv", { method: "POST", body: JSON.stringify({ csv }) }),
};
