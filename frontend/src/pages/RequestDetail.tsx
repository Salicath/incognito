import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import EmailThread from "../components/EmailThread";
import { ArrowLeft, Clock, Send, CheckCircle, XCircle, AlertTriangle, ExternalLink, FileText, Copy, Loader2, Mail } from "lucide-react";

interface RequestDetail {
  id: string;
  broker_id: string;
  request_type: string;
  status: string;
  sent_at: string | null;
  deadline_at: string | null;
  response_at: string | null;
  response_body: string | null;
  created_at: string | null;
  updated_at: string | null;
  broker?: {
    name: string;
    domain: string;
    dpo_email: string;
    removal_method: string;
    country: string;
    language: string;
  };
  email_messages?: Array<{
    id: number;
    direction: "inbound" | "outbound";
    from_address: string;
    to_address: string;
    subject: string;
    body_text: string;
    received_at: string | null;
  }>;
}

interface EventItem {
  id: number;
  event_type: string;
  details: string | null;
  created_at: string | null;
}

export default function RequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [request, setRequest] = useState<RequestDetail | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState("");
  const [complaint, setComplaint] = useState<{
    complaint_text: string;
    dpa: { name: string; short_name: string; email: string | null; url: string } | null;
  } | null>(null);
  const [complaintLoading, setComplaintLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ type: string; text: string } | null>(null);

  useEffect(() => {
    if (id) loadData(id);
  }, [id]);

  async function loadData(requestId: string) {
    try {
      const [req, evts] = await Promise.all([
        api.getRequest(requestId) as unknown as Promise<RequestDetail>,
        api.getRequestEvents(requestId) as unknown as Promise<EventItem[]>,
      ]);
      setRequest(req);
      setEvents(evts);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }

  async function handleAction(action: string, details?: string) {
    if (!id) return;
    setActionLoading(action);
    try {
      await api.transitionRequest(id, action, details);
      await loadData(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setActionLoading("");
    }
  }

  async function handleGenerateComplaint() {
    if (!id) return;
    setComplaintLoading(true);
    try {
      const result = await api.generateComplaint(id);
      setComplaint({ complaint_text: result.complaint_text, dpa: result.dpa });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate complaint");
    } finally {
      setComplaintLoading(false);
    }
  }

  async function handleCopyComplaint() {
    if (!complaint) return;
    await navigator.clipboard.writeText(complaint.complaint_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (!request) {
    return <div className="p-8 text-gray-500">{error || "Loading..."}</div>;
  }

  const daysLeft = request.deadline_at
    ? Math.ceil((new Date(request.deadline_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    : null;

  return (
    <div className="p-8 max-w-3xl">
      <button
        onClick={() => navigate("/requests")}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-6"
      >
        <ArrowLeft className="w-4 h-4" /> Back to requests
      </button>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{error}</div>
      )}

      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold">
              {request.broker?.name || request.broker_id}
            </h1>
            {request.broker && (
              <p className="text-sm text-gray-500 mt-1">
                {request.broker.domain} · {request.broker.country} · {request.broker.dpo_email}
              </p>
            )}
          </div>
          <StatusBadge status={request.status} />
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Request type:</span>
            <span className="ml-2 font-medium">
              {request.request_type === "access" ? "Art. 15 — Access" : "Art. 17 — Erasure"}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Created:</span>
            <span className="ml-2">{request.created_at ? new Date(request.created_at).toLocaleDateString() : "—"}</span>
          </div>
          {request.sent_at && (
            <div>
              <span className="text-gray-500">Sent:</span>
              <span className="ml-2">{new Date(request.sent_at).toLocaleDateString()}</span>
            </div>
          )}
          {request.deadline_at && (
            <div>
              <span className="text-gray-500">Deadline:</span>
              <span className={`ml-2 font-medium ${daysLeft !== null && daysLeft < 0 ? "text-red-600" : daysLeft !== null && daysLeft < 7 ? "text-orange-600" : ""}`}>
                {new Date(request.deadline_at).toLocaleDateString()}
                {daysLeft !== null && (
                  <span className="ml-1">
                    ({daysLeft > 0 ? `${daysLeft} days left` : daysLeft === 0 ? "due today" : `${Math.abs(daysLeft)} days overdue`})
                  </span>
                )}
              </span>
            </div>
          )}
        </div>

        {request.response_body && (
          <div className="mt-4 p-3 bg-gray-50 rounded-lg">
            <p className="text-xs text-gray-500 mb-1">Response:</p>
            <p className="text-sm">{request.response_body}</p>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
        <h2 className="font-semibold mb-3">Actions</h2>
        <div className="flex flex-wrap gap-2">
          {request.status === "created" && (
            <button onClick={() => handleAction("mark_sent")} disabled={!!actionLoading}
              className="flex items-center gap-1 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 transition disabled:opacity-50">
              <Send className="w-3.5 h-3.5" /> Mark as Sent
            </button>
          )}
          {request.status === "sent" && (
            <>
              <button onClick={() => setPendingAction({ type: "mark_acknowledged", text: "" })} disabled={!!actionLoading}
                className="flex items-center gap-1 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 transition disabled:opacity-50">
                <CheckCircle className="w-3.5 h-3.5" /> Mark Acknowledged
              </button>
              <button onClick={() => handleAction("mark_overdue")} disabled={!!actionLoading}
                className="flex items-center gap-1 px-4 py-2 bg-orange-600 text-white rounded-lg text-sm hover:bg-orange-700 transition disabled:opacity-50">
                <Clock className="w-3.5 h-3.5" /> Mark Overdue
              </button>
            </>
          )}
          {request.status === "acknowledged" && (
            <>
              <button onClick={() => handleAction("mark_completed")} disabled={!!actionLoading}
                className="flex items-center gap-1 px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 transition disabled:opacity-50">
                <CheckCircle className="w-3.5 h-3.5" /> Mark Completed
              </button>
              <button onClick={() => setPendingAction({ type: "mark_refused", text: "" })} disabled={!!actionLoading}
                className="flex items-center gap-1 px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 transition disabled:opacity-50">
                <XCircle className="w-3.5 h-3.5" /> Mark Refused
              </button>
            </>
          )}
          {(request.status === "overdue" || request.status === "refused") && (
            <button onClick={() => handleAction("mark_escalated")} disabled={!!actionLoading}
              className="flex items-center gap-1 px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 transition disabled:opacity-50">
              <AlertTriangle className="w-3.5 h-3.5" /> Escalate
            </button>
          )}
          {request.status === "manual_action_needed" && (
            <>
              <button onClick={() => handleAction("mark_sent")} disabled={!!actionLoading}
                className="flex items-center gap-1 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700 transition disabled:opacity-50">
                <Send className="w-3.5 h-3.5" /> Mark as Sent (manual)
              </button>
              <button onClick={() => handleAction("mark_completed")} disabled={!!actionLoading}
                className="flex items-center gap-1 px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 transition disabled:opacity-50">
                <CheckCircle className="w-3.5 h-3.5" /> Mark Completed
              </button>
            </>
          )}
          {request.broker && (
            <a href={`https://${request.broker.domain}`} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1 px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 transition">
              <ExternalLink className="w-3.5 h-3.5" /> Visit Site
            </a>
          )}
        </div>
        {pendingAction && (
          <div className="mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {pendingAction.type === "mark_acknowledged" ? "Broker's response:" : "Reason for refusal:"}
            </label>
            <textarea
              value={pendingAction.text}
              onChange={(e) => setPendingAction({ ...pendingAction, text: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none dark:bg-gray-800 dark:border-gray-600 dark:text-gray-100"
              rows={3}
              placeholder={pendingAction.type === "mark_acknowledged" ? "Paste or describe the broker's response..." : "Why did the broker refuse?"}
              autoFocus
            />
            <div className="flex gap-2 mt-2">
              <button
                onClick={() => {
                  handleAction(pendingAction.type, pendingAction.text);
                  setPendingAction(null);
                }}
                disabled={!pendingAction.text.trim() || !!actionLoading}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition disabled:opacity-50"
              >
                Confirm
              </button>
              <button
                onClick={() => setPendingAction(null)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 transition dark:border-gray-600 dark:hover:bg-gray-800"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Email Thread */}
      {request.email_messages && request.email_messages.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Mail className="w-4 h-4 text-gray-500" />
            <h2 className="font-semibold">Emails ({request.email_messages.length})</h2>
          </div>
          <EmailThread emails={request.email_messages} />
        </div>
      )}

      {/* DPA Complaint — for escalated/overdue/refused requests */}
      {(request.status === "escalated" || request.status === "overdue" || request.status === "refused") && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">DPA Complaint</h2>
            {!complaint && (
              <button
                onClick={handleGenerateComplaint}
                disabled={complaintLoading}
                className="flex items-center gap-1 px-4 py-2 bg-red-600 text-white rounded-lg text-sm hover:bg-red-700 transition disabled:opacity-50"
              >
                {complaintLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                Generate Complaint
              </button>
            )}
          </div>
          {!complaint && (
            <p className="text-sm text-gray-500">
              Generate a pre-filled complaint to send to the relevant Data Protection Authority.
              They can fine the broker up to 4% of annual revenue for non-compliance.
            </p>
          )}
          {complaint && (
            <div>
              {complaint.dpa && (
                <div className="bg-gray-50 rounded-lg p-3 mb-3 text-sm">
                  <p className="font-medium">{complaint.dpa.name}</p>
                  {complaint.dpa.email && <p className="text-gray-500">Email: {complaint.dpa.email}</p>}
                  <a href={complaint.dpa.url} target="_blank" rel="noopener noreferrer"
                    className="text-indigo-600 hover:underline flex items-center gap-1 mt-1">
                    <ExternalLink className="w-3 h-3" /> Submit complaint online
                  </a>
                </div>
              )}
              <pre className="bg-gray-50 rounded-lg p-4 text-xs whitespace-pre-wrap max-h-64 overflow-y-auto mb-3">
                {complaint.complaint_text}
              </pre>
              <button
                onClick={handleCopyComplaint}
                className="flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                <Copy className="w-3.5 h-3.5" />
                {copied ? "Copied!" : "Copy to clipboard"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Event Timeline */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="font-semibold mb-4">Timeline</h2>
        {events.length === 0 ? (
          <p className="text-sm text-gray-500">No events yet.</p>
        ) : (
          <div className="border-l-2 border-gray-200 ml-2 space-y-4">
            {events.map((event) => (
              <div key={event.id} className="relative pl-6">
                <div className="absolute -left-[9px] top-1 w-4 h-4 rounded-full bg-white border-2 border-indigo-400" />
                <div>
                  <p className="text-sm font-medium text-gray-900">{event.event_type.replace(/_/g, " ")}</p>
                  {event.details && <p className="text-xs text-gray-500 mt-0.5">{event.details}</p>}
                  {event.created_at && (
                    <p className="text-xs text-gray-400 mt-0.5">{new Date(event.created_at).toLocaleString()}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
