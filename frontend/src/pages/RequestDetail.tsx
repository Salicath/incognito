import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import StatusBadge from "../components/StatusBadge";
import { ArrowLeft, Clock, Send, CheckCircle, XCircle, AlertTriangle, ExternalLink } from "lucide-react";

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
              <button onClick={() => {
                const body = prompt("Enter the broker's response:");
                if (body) handleAction("mark_acknowledged", body);
              }} disabled={!!actionLoading}
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
              <button onClick={() => {
                const reason = prompt("Reason for refusal:");
                if (reason) handleAction("mark_refused", reason);
              }} disabled={!!actionLoading}
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
      </div>

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
