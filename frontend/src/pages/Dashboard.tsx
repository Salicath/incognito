import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Send, CheckCircle, Clock, AlertTriangle } from "lucide-react";
import StatusBadge from "../components/StatusBadge";

interface Stats { total: number; created: number; sent: number; acknowledged: number; completed: number; refused: number; overdue: number; escalated: number; manual_action_needed: number; }

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [recentRequests, setRecentRequests] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    api.getStats().then((s) => setStats(s as unknown as Stats));
    api.getRequests().then((r) => setRecentRequests(r.slice(0, 10)));
  }, []);

  if (!stats) return <div className="p-8 text-gray-500">Loading...</div>;

  const cards = [
    { label: "Pending", value: stats.created, icon: Clock, color: "text-yellow-600 bg-yellow-50" },
    { label: "Sent", value: stats.sent, icon: Send, color: "text-blue-600 bg-blue-50" },
    { label: "Completed", value: stats.completed, icon: CheckCircle, color: "text-green-600 bg-green-50" },
    { label: "Overdue", value: stats.overdue + stats.manual_action_needed, icon: AlertTriangle, color: "text-red-600 bg-red-50" },
  ];

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-4 gap-4 mb-8">
        {cards.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-500">{label}</span>
              <div className={`p-2 rounded-lg ${color}`}><Icon className="w-4 h-4" /></div>
            </div>
            <p className="text-3xl font-bold">{value}</p>
          </div>
        ))}
      </div>
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="px-5 py-4 border-b border-gray-200"><h2 className="font-semibold">Recent Activity</h2></div>
        {recentRequests.length === 0 ? (
          <p className="px-5 py-8 text-gray-500 text-center text-sm">No requests yet. Browse brokers to get started.</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {recentRequests.map((req) => (
              <div key={req.id as string} className="px-5 py-3 flex items-center justify-between text-sm">
                <div><span className="font-medium">{req.broker_id as string}</span><span className="text-gray-400 mx-2">·</span><span className="text-gray-500">{req.request_type as string}</span></div>
                <StatusBadge status={req.status as string} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
