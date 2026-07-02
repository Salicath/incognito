import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import { Inbox, ExternalLink, CheckCircle, XCircle, Ban, RotateCcw, Loader2, AlertTriangle, Send } from "lucide-react";

interface Exposure {
  id: number;
  source: string;
  source_label: string;
  title: string;
  url: string;
  data: Record<string, unknown>;
  scanned_at: string | null;
  disposition: string | null;
  note: string;
  matched_broker: { broker_id: string; name: string } | null;
  guidance: { title: string; steps: string[]; links: Array<{ label: string; url: string }> } | null;
}

interface Summary {
  total: number;
  needs_triage: number;
  actioned: number;
  dismissed: number;
  legally_impossible: number;
}

type Filter = "needs_triage" | "actioned" | "dismissed" | "legally_impossible" | "all";

const sourceColors: Record<string, string> = {
  duckduckgo: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  holehe: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  wayback: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  github: "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200",
};

const dispositionMeta: Record<string, { label: string; className: string }> = {
  actioned: { label: "Actioned", className: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
  dismissed: { label: "Dismissed", className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400" },
  legally_impossible: { label: "Can't delete", className: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
};

// Pull the most useful secondary line out of the source-specific found_data.
function detailLine(e: Exposure): string {
  const d = e.data;
  const parts: string[] = [];
  if (typeof d.path === "string") parts.push(d.path);
  if (typeof d.username === "string") parts.push(`@${d.username}`);
  if (typeof d.identifier === "string") parts.push(d.identifier);
  if (typeof d.snapshots === "number") parts.push(`${d.snapshots} snapshot${d.snapshots === 1 ? "" : "s"}`);
  if (typeof d.snippet === "string" && d.snippet) parts.push(d.snippet);
  return parts.join(" · ");
}

export default function Exposures() {
  const [exposures, setExposures] = useState<Exposure[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("needs_triage");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.getExposures();
      setExposures(data.exposures);
      setSummary(data.summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load exposures");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function setDisposition(id: number, disposition: string | null) {
    setBusy(id);
    try {
      await api.setExposureDisposition(id, disposition, notes[id] ?? "");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update");
    } finally {
      setBusy(null);
    }
  }

  async function createRequest(id: number) {
    setBusy(id);
    try {
      await api.createRequestFromExposure(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create request");
    } finally {
      setBusy(null);
    }
  }

  const visible = exposures.filter((e) =>
    filter === "all" ? true : filter === "needs_triage" ? e.disposition === null : e.disposition === filter
  );

  const filters: Array<{ key: Filter; label: string; count: number | undefined }> = [
    { key: "needs_triage", label: "Needs triage", count: summary?.needs_triage },
    { key: "actioned", label: "Actioned", count: summary?.actioned },
    { key: "dismissed", label: "Dismissed", count: summary?.dismissed },
    { key: "legally_impossible", label: "Can't delete", count: summary?.legally_impossible },
    { key: "all", label: "All", count: summary?.total },
  ];

  if (loading) {
    return <div className="flex items-center justify-center h-64"><p className="text-gray-500 dark:text-gray-400">Loading exposures...</p></div>;
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Inbox className="w-6 h-6 text-indigo-500" /> Exposures
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Every scan hit across all sources in one queue. Route each to a resolution so nothing slips through.
        </p>
      </div>

      {error && <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">{error}</div>}

      {summary && summary.total === 0 ? (
        <div className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-12 text-center">
          <Inbox className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">No exposures yet</h2>
          <p className="text-gray-500 dark:text-gray-400 text-sm max-w-md mx-auto">
            Run the scanners on the Scan page. Every hit — web search, account, archive, code leak — lands here for triage.
          </p>
        </div>
      ) : (
        <>
          {/* Filter tabs */}
          <div className="flex flex-wrap gap-2 mb-5">
            {filters.map((f) => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                  filter === f.key
                    ? "bg-indigo-600 text-white"
                    : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700"
                }`}
              >
                {f.label}{f.count !== undefined ? ` (${f.count})` : ""}
              </button>
            ))}
          </div>

          {summary && summary.needs_triage > 0 && filter === "needs_triage" && (
            <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400 mb-4">
              <AlertTriangle className="w-4 h-4" />
              {summary.needs_triage} exposure{summary.needs_triage === 1 ? "" : "s"} awaiting a decision.
            </div>
          )}

          {visible.length === 0 ? (
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-10 text-center text-gray-500 dark:text-gray-400 text-sm">
              Nothing in this view.
            </div>
          ) : (
            <div className="space-y-3">
              {visible.map((e) => {
                const detail = detailLine(e);
                const disp = e.disposition ? dispositionMeta[e.disposition] : null;
                return (
                  <div key={e.id} className="bg-white dark:bg-gray-900 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${sourceColors[e.source] ?? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"}`}>
                            {e.source_label}
                          </span>
                          <span className="font-medium text-sm truncate">{e.title}</span>
                          {disp && <span className={`px-2 py-0.5 rounded text-xs font-medium ${disp.className}`}>{disp.label}</span>}
                        </div>
                        {detail && <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{detail}</p>}
                        {e.disposition && e.note && (
                          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 italic">“{e.note}”</p>
                        )}
                      </div>
                      {e.url && (
                        <a href={e.url} target="_blank" rel="noopener noreferrer"
                          className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition shrink-0">
                          <ExternalLink className="w-3 h-3" /> Open
                        </a>
                      )}
                    </div>

                    {/* Removal guidance for exposures with no registry broker */}
                    {e.guidance && (
                      <details className="mt-3 group">
                        <summary className="text-xs font-medium text-indigo-600 dark:text-indigo-400 cursor-pointer hover:text-indigo-700 dark:hover:text-indigo-300 select-none">
                          How to remove this →
                        </summary>
                        <div className="mt-2 pl-3 border-l-2 border-indigo-100 dark:border-indigo-900/50">
                          <p className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">{e.guidance.title}</p>
                          <ol className="list-decimal list-inside space-y-1.5 text-xs text-gray-600 dark:text-gray-300">
                            {e.guidance.steps.map((step, si) => <li key={si}>{step}</li>)}
                          </ol>
                          {e.guidance.links.length > 0 && (
                            <div className="flex flex-wrap gap-3 mt-2.5">
                              {e.guidance.links.map((link) => (
                                <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
                                  <ExternalLink className="w-3 h-3" /> {link.label}
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
                      </details>
                    )}

                    {/* Action bar */}
                    <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
                      {e.disposition === null ? (
                        <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
                          <input
                            type="text"
                            placeholder="Optional note (what you did / why)"
                            value={notes[e.id] ?? ""}
                            onChange={(ev) => setNotes({ ...notes, [e.id]: ev.target.value })}
                            className="flex-1 px-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 dark:text-gray-100 outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                          />
                          <div className="flex gap-2 shrink-0 flex-wrap">
                            {e.matched_broker && (
                              <button onClick={() => createRequest(e.id)} disabled={busy === e.id}
                                title={`Create an Art. 17 erasure request for ${e.matched_broker.name}`}
                                className="flex items-center gap-1 px-3 py-1.5 text-xs bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 transition disabled:opacity-50">
                                {busy === e.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />} Create erasure request
                              </button>
                            )}
                            <button onClick={() => setDisposition(e.id, "actioned")} disabled={busy === e.id}
                              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition disabled:opacity-50">
                              {busy === e.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />} {e.matched_broker ? "Mark actioned" : "Actioned"}
                            </button>
                            <button onClick={() => setDisposition(e.id, "dismissed")} disabled={busy === e.id}
                              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-lg font-medium hover:bg-gray-200 dark:hover:bg-gray-700 transition disabled:opacity-50">
                              <XCircle className="w-3 h-3" /> Dismiss
                            </button>
                            <button onClick={() => setDisposition(e.id, "legally_impossible")} disabled={busy === e.id}
                              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-lg font-medium hover:bg-blue-100 dark:hover:bg-blue-900/50 transition disabled:opacity-50">
                              <Ban className="w-3 h-3" /> Can't delete
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button onClick={() => setDisposition(e.id, null)} disabled={busy === e.id}
                          className="flex items-center gap-1 px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition disabled:opacity-50">
                          {busy === e.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />} Reset to triage
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
