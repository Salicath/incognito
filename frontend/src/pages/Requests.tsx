import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Send, Eye } from "lucide-react";
import StatusBadge from "../components/StatusBadge";

interface RequestItem { id: string; broker_id: string; request_type: string; status: string; sent_at: string | null; deadline_at: string | null; created_at: string | null; }
interface RequestEvent { id: number; event_type: string; details: string | null; created_at: string | null; }

export default function Requests() {
  const navigate = useNavigate();
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<RequestEvent[]>([]);

  useEffect(() => { loadRequests(); }, [filter]);

  async function loadRequests() {
    const data = await api.getRequests(filter || undefined);
    setRequests(data as unknown as RequestItem[]);
  }

  async function viewEvents(id: string) {
    if (selectedId === id) { setSelectedId(null); return; }
    const data = await api.getRequestEvents(id);
    setEvents(data as unknown as RequestEvent[]);
    setSelectedId(id);
  }

  async function handleTransition(id: string, action: string) {
    await api.transitionRequest(id, action);
    loadRequests();
  }

  const statusFilters = ["", "created", "sent", "acknowledged", "completed", "refused", "overdue", "escalated", "manual_action_needed"];

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-6">Requests</h1>
      <div className="flex gap-2 mb-4 flex-wrap">
        {statusFilters.map((s) => (
          <button key={s} onClick={() => setFilter(s)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${filter === s ? "bg-indigo-600 text-white" : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"}`}>{s || "All"}</button>
        ))}
      </div>
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        {requests.length === 0 ? (
          <p className="px-5 py-8 text-gray-500 text-center text-sm">No requests found.</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {requests.map((req) => (
              <div key={req.id}>
                <div className="px-5 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between text-sm gap-2">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
                    <span className="font-medium sm:w-40 truncate cursor-pointer hover:text-indigo-600"
                      onClick={() => navigate(`/requests/${req.id}`)}>
                      {req.broker_id}
                    </span>
                    <span className="hidden sm:block text-gray-500 w-24">{req.request_type}</span>
                    <StatusBadge status={req.status} />
                  </div>
                  <div className="flex items-center gap-2">
                    {req.status === "created" && (
                      <button onClick={() => handleTransition(req.id, "mark_sent")} className="flex items-center gap-1 px-3 py-1 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-medium hover:bg-indigo-100 transition"><Send className="w-3 h-3" /> Send</button>
                    )}
                    <button onClick={() => viewEvents(req.id)} className="flex items-center gap-1 px-3 py-1 bg-gray-50 text-gray-600 rounded-lg text-xs hover:bg-gray-100 transition"><Eye className="w-3 h-3" />{selectedId === req.id ? "Hide" : "Events"}</button>
                  </div>
                </div>
                {selectedId === req.id && (
                  <div className="px-5 pb-4 pl-12">
                    <div className="border-l-2 border-indigo-200 pl-4 space-y-2">
                      {events.map((e) => (
                        <div key={e.id} className="text-xs">
                          <span className="font-medium text-indigo-600">{e.event_type}</span>
                          {e.details && <span className="text-gray-500 ml-2">{e.details}</span>}
                          {e.created_at && <span className="text-gray-400 ml-2">{new Date(e.created_at).toLocaleString()}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
