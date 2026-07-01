import { useEffect, useState } from "react";
import { api } from "../api/client";
import { CheckCircle2, ExternalLink, Fingerprint, Loader2, ShieldCheck } from "lucide-react";

interface Lever {
  lever_id: string;
  name: string;
  description: string;
  url: string;
  requires_mitid: boolean;
  expires_after_days: number | null;
  notes: string | null;
  status: string;
  activated_at: string | null;
  expires_at: string | null;
  user_note: string;
  cascade: Array<{ broker_id: string; name: string }>;
  active_conflicts: string[];
}

const statusStyles: Record<string, string> = {
  new: "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200",
  active: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  renewal_due: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  expired: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  user_deferred: "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400",
};

const statusLabels: Record<string, string> = {
  new: "Not started",
  active: "Active",
  renewal_due: "Renewal due",
  expired: "Expired",
  user_deferred: "Deferred",
};

export default function CprLevers() {
  const [levers, setLevers] = useState<Lever[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [deferring, setDeferring] = useState("");
  const [deferNote, setDeferNote] = useState("");

  async function load() {
    try {
      const data = await api.getCprLevers();
      setLevers(data as unknown as Lever[]);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load levers");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleConfirm(id: string) {
    setBusy(id);
    try {
      await api.confirmCprLever(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to confirm lever");
    } finally {
      setBusy("");
    }
  }

  async function handleDefer(id: string) {
    setBusy(id);
    try {
      await api.deferCprLever(id, deferNote);
      setDeferring("");
      setDeferNote("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to defer lever");
    } finally {
      setBusy("");
    }
  }

  const coveredCount = new Set(
    levers
      .filter((lv) => lv.status === "active" || lv.status === "renewal_due")
      .flatMap((lv) => lv.cascade.map((c) => c.broker_id))
  ).size;

  if (loading) {
    return (
      <div className="p-8 flex items-center gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" /> Loading...
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold">CPR Levers</h1>
        {coveredCount > 0 && (
          <div className="flex items-center gap-2 text-sm text-green-700 dark:text-green-300">
            <ShieldCheck className="w-4 h-4" />
            {coveredCount} brokers covered without sending a request
          </div>
        )}
      </div>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-3xl">
        Danish registry-level protections. These require MitID, so Incognito can't perform
        them for you — complete each action on the linked site, then confirm it here. Active
        levers automatically cover their downstream brokers in blasts.
      </p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg text-sm">
          {error}
        </div>
      )}

      <div className="space-y-4">
        {levers.map((lever) => (
          <div
            key={lever.lever_id}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="font-semibold">{lever.name}</h2>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusStyles[lever.status] || statusStyles.new}`}
                  >
                    {statusLabels[lever.status] || lever.status}
                  </span>
                  {lever.requires_mitid && (
                    <span className="flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-300">
                      <Fingerprint className="w-3 h-3" /> MitID
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">{lever.description}</p>
                {lever.notes && (
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{lever.notes}</p>
                )}
                {lever.cascade.length > 0 && (
                  <div className="flex items-center gap-2 mt-3 flex-wrap">
                    <span className="text-xs text-gray-500 dark:text-gray-400">Covers:</span>
                    {lever.cascade.map((c) => (
                      <span
                        key={c.broker_id}
                        className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
                      >
                        {c.name}
                      </span>
                    ))}
                  </div>
                )}
                {lever.expires_at && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                    Expires {lever.expires_at.slice(0, 10)}
                    {lever.status === "renewal_due" && " — renew now"}
                    {lever.status === "expired" && " — protection lapsed, downstream brokers re-exposed"}
                  </p>
                )}
                {lever.status === "user_deferred" && lever.user_note && (
                  <p className="text-xs text-gray-400 italic mt-2">Deferred: {lever.user_note}</p>
                )}
                {lever.active_conflicts.length > 0 && lever.status === "new" && (
                  <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
                    Blocked by CPR registry rule while {lever.active_conflicts.join(", ")} is active.
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-2 shrink-0">
                {lever.url && (
                  <a
                    href={lever.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-center gap-1.5 px-3 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                  >
                    Open <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
                {lever.status !== "active" && lever.active_conflicts.length === 0 && (
                  <button
                    onClick={() => handleConfirm(lever.lever_id)}
                    disabled={busy === lever.lever_id}
                    className="flex items-center justify-center gap-1.5 px-3 py-2 text-sm border border-green-600 text-green-700 dark:text-green-300 rounded-lg hover:bg-green-50 dark:hover:bg-green-900/30 disabled:opacity-50"
                  >
                    {busy === lever.lever_id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    )}
                    I did this
                  </button>
                )}
                {(lever.status === "new" || lever.status === "user_notified") && (
                  <button
                    onClick={() => setDeferring(deferring === lever.lever_id ? "" : lever.lever_id)}
                    className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                  >
                    Defer
                  </button>
                )}
              </div>
            </div>

            {deferring === lever.lever_id && (
              <div className="mt-3 flex gap-2">
                <input
                  type="text"
                  value={deferNote}
                  onChange={(e) => setDeferNote(e.target.value)}
                  placeholder="Why defer? (optional)"
                  className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900"
                />
                <button
                  onClick={() => handleDefer(lever.lever_id)}
                  disabled={busy === lever.lever_id}
                  className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
                >
                  Confirm defer
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
