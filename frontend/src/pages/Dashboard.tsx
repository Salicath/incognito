import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Send, CheckCircle, Clock, AlertTriangle, Zap, Shield, Loader2 } from "lucide-react";
import StatusBadge from "../components/StatusBadge";

interface Stats { total: number; created: number; sent: number; acknowledged: number; completed: number; refused: number; overdue: number; escalated: number; manual_action_needed: number; }

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [recentRequests, setRecentRequests] = useState<Array<Record<string, unknown>>>([]);
  const [blastLoading, setBlastLoading] = useState(false);
  const [blastResult, setBlastResult] = useState<{ created: number; skipped: number } | null>(null);
  const [sendLoading, setSendLoading] = useState(false);
  const [sendResult, setSendResult] = useState<{ sent: number; failed: number; manual: number } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { loadData(); }, []);

  function loadData() {
    api.getStats().then((s) => setStats(s as unknown as Stats));
    api.getRequests().then((r) => setRecentRequests(r.slice(0, 10)));
  }

  async function handleBlast(type: string) {
    setBlastLoading(true);
    setError("");
    setBlastResult(null);
    setSendResult(null);
    try {
      const result = await api.blastCreate(type, false);
      setBlastResult({ created: result.created, skipped: result.skipped });
      loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create requests");
    } finally {
      setBlastLoading(false);
    }
  }

  async function handleSendAll() {
    setSendLoading(true);
    setError("");
    setSendResult(null);
    try {
      const result = await api.blastSendAll();
      setSendResult({ sent: result.sent, failed: result.failed, manual: result.manual });
      loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send requests");
    } finally {
      setSendLoading(false);
    }
  }

  if (!stats) return <div className="p-8 text-gray-500">Loading...</div>;

  const hasNoRequests = stats.total === 0;
  const hasPending = stats.created > 0;

  const statCards = [
    { label: "Pending", value: stats.created, icon: Clock, color: "text-yellow-600 bg-yellow-50" },
    { label: "Sent", value: stats.sent, icon: Send, color: "text-blue-600 bg-blue-50" },
    { label: "Completed", value: stats.completed, icon: CheckCircle, color: "text-green-600 bg-green-50" },
    { label: "Needs Attention", value: stats.overdue + stats.manual_action_needed + stats.refused, icon: AlertTriangle, color: "text-red-600 bg-red-50" },
  ];

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {/* Blast action card - the main CTA */}
      {hasNoRequests && (
        <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 rounded-2xl p-8 mb-8 text-white">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-white/10 rounded-xl">
              <Shield className="w-8 h-8" />
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-bold mb-2">Take back your privacy</h2>
              <p className="text-indigo-200 mb-6 max-w-xl">
                Send legally-binding GDPR requests to all 145 data brokers in our registry.
                Under Article 15, they must respond within 30 days or face regulatory action.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => handleBlast("access")}
                  disabled={blastLoading}
                  className="flex items-center gap-2 px-5 py-2.5 bg-white text-indigo-700 rounded-lg font-medium hover:bg-indigo-50 transition disabled:opacity-50"
                >
                  {blastLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  Send Art. 15 to all brokers
                </button>
                <button
                  onClick={() => handleBlast("erasure")}
                  disabled={blastLoading}
                  className="flex items-center gap-2 px-5 py-2.5 bg-white/10 text-white border border-white/20 rounded-lg font-medium hover:bg-white/20 transition disabled:opacity-50"
                >
                  Send Art. 17 to all brokers
                </button>
              </div>
              <p className="text-indigo-300 text-xs mt-3">
                Art. 15 = "Do you have my data?" &middot; Art. 17 = "Delete my data"
              </p>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{error}</div>
      )}

      {blastResult && (
        <div className="bg-green-50 border border-green-200 text-green-800 px-5 py-4 rounded-xl mb-6">
          <p className="font-medium">
            {blastResult.created} requests created
            {blastResult.skipped > 0 && <span className="text-green-600 font-normal"> ({blastResult.skipped} skipped — already have active requests)</span>}
          </p>
          {blastResult.created > 0 && (
            <div className="mt-3">
              <button
                onClick={handleSendAll}
                disabled={sendLoading}
                className="flex items-center gap-2 px-4 py-2 bg-green-700 text-white rounded-lg text-sm font-medium hover:bg-green-800 transition disabled:opacity-50"
              >
                {sendLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                {sendLoading ? "Sending..." : `Send all ${blastResult.created} requests now`}
              </button>
              <p className="text-green-600 text-xs mt-2">Requires SMTP to be configured in settings.</p>
            </div>
          )}
        </div>
      )}

      {sendResult && (
        <div className="bg-blue-50 border border-blue-200 text-blue-800 px-5 py-4 rounded-xl mb-6">
          <p className="font-medium">
            {sendResult.sent} sent
            {sendResult.failed > 0 && <span className="text-red-600"> &middot; {sendResult.failed} failed</span>}
            {sendResult.manual > 0 && <span className="text-yellow-600"> &middot; {sendResult.manual} need manual action</span>}
          </p>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        {statCards.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-500">{label}</span>
              <div className={`p-2 rounded-lg ${color}`}><Icon className="w-4 h-4" /></div>
            </div>
            <p className="text-3xl font-bold">{value}</p>
          </div>
        ))}
      </div>

      {/* Pending blast actions for returning users */}
      {!hasNoRequests && hasPending && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl px-5 py-4 mb-6 flex items-center justify-between">
          <div>
            <p className="font-medium text-yellow-900">{stats.created} requests ready to send</p>
            <p className="text-yellow-700 text-sm">These have been created but not yet sent via email.</p>
          </div>
          <button
            onClick={handleSendAll}
            disabled={sendLoading}
            className="flex items-center gap-2 px-4 py-2 bg-yellow-600 text-white rounded-lg text-sm font-medium hover:bg-yellow-700 transition disabled:opacity-50"
          >
            {sendLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Send all
          </button>
        </div>
      )}

      {/* Quick blast buttons for returning users */}
      {!hasNoRequests && !hasPending && (
        <div className="flex gap-3 mb-6">
          <button
            onClick={() => handleBlast("access")}
            disabled={blastLoading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition disabled:opacity-50"
          >
            {blastLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Blast Art. 15 to all
          </button>
          <button
            onClick={() => handleBlast("erasure")}
            disabled={blastLoading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-100 text-indigo-700 rounded-lg text-sm font-medium hover:bg-indigo-200 transition disabled:opacity-50"
          >
            Blast Art. 17 to all
          </button>
        </div>
      )}

      {/* Recent activity */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="px-5 py-4 border-b border-gray-200"><h2 className="font-semibold">Recent Activity</h2></div>
        {recentRequests.length === 0 ? (
          <p className="px-5 py-8 text-gray-500 text-center text-sm">No requests yet. Use the blast above to get started.</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {recentRequests.map((req) => (
              <div key={req.id as string} className="px-5 py-3 flex items-center justify-between text-sm">
                <div><span className="font-medium">{req.broker_id as string}</span><span className="text-gray-400 mx-2">&middot;</span><span className="text-gray-500">{req.request_type as string}</span></div>
                <StatusBadge status={req.status as string} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
