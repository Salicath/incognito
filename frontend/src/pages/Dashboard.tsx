import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useNavigate } from "react-router-dom";
import { Send, Clock, Zap, Shield, Loader2, Search } from "lucide-react";
import StatusBadge from "../components/StatusBadge";
import ProgressRing from "../components/ProgressRing";

interface Stats {
  total: number;
  broker_count: number;
  created: number;
  sent: number;
  acknowledged: number;
  completed: number;
  refused: number;
  overdue: number;
  escalated: number;
  manual_action_needed: number;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<Stats | null>(null);
  const [recentRequests, setRecentRequests] = useState<Array<Record<string, unknown>>>([]);
  const [blastLoading, setBlastLoading] = useState(false);
  const [blastResult, setBlastResult] = useState<{ created: number; skipped: number } | null>(null);
  const [sendLoading, setSendLoading] = useState(false);
  const [sendResult, setSendResult] = useState<{ sent: number; failed: number; manual: number } | null>(null);
  const [followUpLoading, setFollowUpLoading] = useState(false);
  const [followUpResult, setFollowUpResult] = useState<{ newly_overdue: number; follow_ups_sent: number; escalations_sent: number } | null>(null);
  const [error, setError] = useState("");
  const [confirmBlast, setConfirmBlast] = useState<{ type: string; count: number } | null>(null);

  useEffect(() => { loadData(); }, []);

  function loadData() {
    api.getStats().then((s) => setStats(s as unknown as Stats));
    api.getRequests().then((r) => setRecentRequests(r.slice(0, 10)));
  }

  async function handleBlastPreview(type: string) {
    setBlastLoading(true);
    setError("");
    try {
      const result = await api.blastCreate(type, true);
      setConfirmBlast({ type, count: result.created });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to preview requests");
    } finally {
      setBlastLoading(false);
    }
  }

  async function handleBlastConfirm() {
    if (!confirmBlast) return;
    setBlastLoading(true);
    setError("");
    setBlastResult(null);
    setSendResult(null);
    try {
      const result = await api.blastCreate(confirmBlast.type, false);
      setBlastResult({ created: result.created, skipped: result.skipped });
      setConfirmBlast(null);
      loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create requests");
    } finally {
      setBlastLoading(false);
    }
  }

  async function handleFollowUp() {
    setFollowUpLoading(true);
    try {
      const result = await api.runFollowUp();
      setFollowUpResult(result);
      loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Follow-up check failed");
    } finally {
      setFollowUpLoading(false);
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

  // Progress metrics
  const resolved = stats.completed;
  const inProgress = stats.sent + stats.acknowledged;
  const needsAttention = stats.overdue + stats.manual_action_needed + stats.refused;
  const contacted = stats.total;
  const brokerCount = stats.broker_count;
  const progressPct = brokerCount > 0 ? Math.round((resolved / brokerCount) * 100) : 0;
  const contactedPct = brokerCount > 0 ? Math.round((contacted / brokerCount) * 100) : 0;

  // Ring color based on progress
  const ringColor = progressPct >= 80 ? "#16a34a" : progressPct >= 40 ? "#4f46e5" : "#6366f1";

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {/* Hero metric — only shown when there are requests */}
      {!hasNoRequests && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 mb-8">
          <div className="flex items-center gap-8">
            <div className="relative flex items-center justify-center">
              <ProgressRing
                percentage={progressPct}
                size={130}
                strokeWidth={12}
                color={ringColor}
                trackColor="#e5e7eb"
              />
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-bold">{progressPct}%</span>
                <span className="text-xs text-gray-500">resolved</span>
              </div>
            </div>
            <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <p className="text-2xl font-bold text-green-600">{resolved}</p>
                <p className="text-xs text-gray-500">Resolved</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-600">{inProgress}</p>
                <p className="text-xs text-gray-500">In progress</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-orange-600">{needsAttention}</p>
                <p className="text-xs text-gray-500">Needs attention</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-700 dark:text-gray-300">{contacted}<span className="text-sm font-normal text-gray-400">/{brokerCount}</span></p>
                <p className="text-xs text-gray-500">Brokers contacted</p>
              </div>
            </div>
          </div>
          {contactedPct < 100 && contacted > 0 && (
            <div className="mt-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>{contacted} of {brokerCount} brokers contacted</span>
                <span>{contactedPct}%</span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                <div
                  className="bg-indigo-500 h-1.5 rounded-full transition-all duration-500"
                  style={{ width: `${contactedPct}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Getting started — scan first prompt */}
      {hasNoRequests && (
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 mb-6">
          <div className="flex items-start gap-4">
            <div className="p-2.5 bg-violet-100 rounded-xl">
              <Search className="w-6 h-6 text-violet-600" />
            </div>
            <div className="flex-1">
              <h2 className="font-semibold text-gray-900 mb-1">See where your data is exposed</h2>
              <p className="text-sm text-gray-500 mb-4">
                Before sending removal requests, run a scan to see which sites already have your data.
                This checks data broker sites, known breaches, and online accounts.
              </p>
              <button
                onClick={() => navigate("/scan")}
                className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 transition"
              >
                <Search className="w-4 h-4" /> Scan for my data
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Blast action card — first-time CTA */}
      {hasNoRequests && (
        <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 rounded-2xl p-8 mb-8 text-white">
          <div className="flex items-start gap-4">
            <div className="p-3 bg-white/10 rounded-xl">
              <Shield className="w-8 h-8" />
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-bold mb-2">Take back your privacy</h2>
              <p className="text-indigo-200 mb-6 max-w-xl">
                Send legally-binding GDPR requests to all {brokerCount} data brokers in our registry.
                Under Article 15, they must respond within 30 days or face regulatory action.
              </p>
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => handleBlastPreview("access")}
                  disabled={blastLoading}
                  className="flex items-center gap-2 px-5 py-2.5 bg-white text-indigo-700 rounded-lg font-medium hover:bg-indigo-50 transition disabled:opacity-50"
                >
                  {blastLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  Send Art. 15 to all brokers
                </button>
                <button
                  onClick={() => handleBlastPreview("erasure")}
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

      {/* Blast confirmation dialog */}
      {confirmBlast && (
        <div className="bg-amber-50 border-2 border-amber-300 rounded-xl px-5 py-5 mb-6">
          <h3 className="font-semibold text-amber-900 mb-2">
            Confirm: Send {confirmBlast.type === "access" ? "Art. 15" : "Art. 17"} to {confirmBlast.count} brokers?
          </h3>
          <p className="text-sm text-amber-800 mb-4">
            This will create {confirmBlast.type === "access" ? "data access" : "data deletion"} requests
            for all {confirmBlast.count} brokers in the registry. Note: sending requests to brokers who
            don't have your data may expose your identity to them. Consider running a scan first to
            identify which brokers actually have your data.
          </p>
          <div className="flex gap-3">
            <button
              onClick={handleBlastConfirm}
              disabled={blastLoading}
              className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 transition disabled:opacity-50"
            >
              {blastLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
              Yes, create {confirmBlast.count} requests
            </button>
            <button
              onClick={() => setConfirmBlast(null)}
              className="px-4 py-2 border border-amber-300 text-amber-700 rounded-lg text-sm font-medium hover:bg-amber-100 transition"
            >
              Cancel
            </button>
            <button
              onClick={() => { setConfirmBlast(null); navigate("/scan"); }}
              className="flex items-center gap-1 px-4 py-2 text-sm text-amber-700 hover:underline"
            >
              <Search className="w-3.5 h-3.5" /> Scan first instead
            </button>
          </div>
        </div>
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

      {/* Deadline monitoring */}
      {stats.sent > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl px-5 py-4 mb-6 flex items-center justify-between">
          <div>
            <p className="font-medium text-gray-900">Deadline monitoring</p>
            <p className="text-gray-500 text-sm">{stats.sent} requests awaiting response. Check for overdue and send follow-ups.</p>
          </div>
          <button onClick={handleFollowUp} disabled={followUpLoading}
            className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg text-sm font-medium hover:bg-orange-700 transition disabled:opacity-50">
            {followUpLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Clock className="w-4 h-4" />}
            Check Deadlines
          </button>
        </div>
      )}

      {followUpResult && (
        <div className="bg-orange-50 border border-orange-200 text-orange-800 px-5 py-4 rounded-xl mb-6">
          <p className="font-medium">
            {followUpResult.newly_overdue} newly overdue
            {followUpResult.follow_ups_sent > 0 && <span> &middot; {followUpResult.follow_ups_sent} follow-ups sent</span>}
            {followUpResult.escalations_sent > 0 && <span> &middot; {followUpResult.escalations_sent} escalations sent</span>}
            {followUpResult.newly_overdue === 0 && followUpResult.follow_ups_sent === 0 && followUpResult.escalations_sent === 0 && " — all requests within deadline"}
          </p>
        </div>
      )}

      {/* Pending send / quick blast buttons */}
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

      {!hasNoRequests && !hasPending && (
        <div className="flex gap-3 mb-6">
          <button
            onClick={() => handleBlastPreview("access")}
            disabled={blastLoading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition disabled:opacity-50"
          >
            {blastLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            Blast Art. 15 to all
          </button>
          <button
            onClick={() => handleBlastPreview("erasure")}
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
