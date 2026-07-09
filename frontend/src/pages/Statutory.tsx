import { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  CheckCircle2,
  ClipboardCopy,
  ExternalLink,
  Fingerprint,
  Hourglass,
  Loader2,
  ShieldOff,
  X,
} from "lucide-react";

interface Hold {
  id: number;
  entry_id: string;
  institution: string;
  trigger_date: string;
  fires_at: string;
  conservative: boolean;
  status: string;
}

interface TimeLockedEntry {
  id: string;
  name: string;
  holder_type: string;
  legal_basis: string;
  trigger_label: string;
  expiry: { years: number; from_fiscal_year_end: boolean; conservative_years: number | null };
  escalation_after_days: number;
  art17_note: string;
  notes: string | null;
  holds: Hold[];
}

interface RestrictionEntry {
  id: string;
  name: string;
  what_it_is: string;
  why_undeletable: string;
  mitigation: string;
  mitigation_url: string;
  requires_mitid: boolean;
  notes: string | null;
}

const holdStyles: Record<string, string> = {
  armed: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  fired: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  dismissed: "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400",
};

export default function Statutory() {
  const [entries, setEntries] = useState<TimeLockedEntry[]>([]);
  const [restrictions, setRestrictions] = useState<RestrictionEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [arming, setArming] = useState("");
  const [triggerDate, setTriggerDate] = useState("");
  const [institution, setInstitution] = useState("");
  const [conservative, setConservative] = useState(false);
  const [kit, setKit] = useState<{ title: string; text: string; escalationDays: number } | null>(null);
  const [copied, setCopied] = useState(false);

  async function load() {
    try {
      const [tl, ro] = await Promise.all([
        api.getTimeLocked(),
        api.getRestrictionOnly(),
      ]);
      setEntries(tl as unknown as TimeLockedEntry[]);
      setRestrictions(ro as unknown as RestrictionEntry[]);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleArm(entryId: string) {
    if (!triggerDate) return;
    setBusy(entryId);
    try {
      await api.armTimeLocked(entryId, triggerDate, institution, conservative);
      setArming("");
      setTriggerDate("");
      setInstitution("");
      setConservative(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to arm");
    } finally {
      setBusy("");
    }
  }

  async function handleDismiss(holdId: number) {
    // no un-dismiss exists — a misclick would silently cancel a multi-year reminder
    if (!window.confirm("Dismiss this hold? The reminder is cancelled permanently.")) return;
    try {
      await api.dismissTimeLockedHold(holdId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to dismiss");
    }
  }

  async function handleKit(hold: Hold, entryName: string) {
    try {
      const resp = await api.getTimeLockedKit(hold.id);
      setKit({
        title: `${entryName}${hold.institution ? ` — ${hold.institution}` : ""}`,
        text: resp.request_text,
        escalationDays: resp.escalation_after_days,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load kit");
    }
  }

  if (loading) {
    return (
      <div className="p-8 flex items-center gap-2 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" /> Loading...
      </div>
    );
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-2 flex items-center gap-2">
        <Hourglass className="w-6 h-6" /> Time-locked erasure
      </h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-3xl">
        Danish statutory retention blocks erasure at these holders until a
        period lapses. Enter the trigger date and Incognito raises the Art. 17
        the day the retention duty matures — at that point "we must keep it"
        is no longer a valid refusal.
      </p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg text-sm">
          {error}
        </div>
      )}

      <div className="space-y-4 mb-10">
        {entries.map((e) => (
          <div
            key={e.id}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="font-semibold">{e.name}</h2>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{e.legal_basis}</p>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">{e.art17_note}</p>
                {e.notes && (
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{e.notes}</p>
                )}

                {e.holds.filter((h) => h.status !== "dismissed").map((h) => (
                  <div key={h.id} className="flex items-center gap-2 mt-3 text-sm flex-wrap">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${holdStyles[h.status]}`}
                    >
                      {h.status === "armed" ? `fires ${h.fires_at}` : h.status}
                    </span>
                    <span className="text-gray-600 dark:text-gray-300">
                      {h.institution || e.holder_type} — trigger {h.trigger_date}
                      {h.conservative ? " (conservative)" : ""}
                    </span>
                    {h.status === "fired" && (
                      <button
                        onClick={() => handleKit(h, e.name)}
                        className="text-xs px-2 py-0.5 rounded border border-green-600 text-green-700 dark:text-green-300 hover:bg-green-50 dark:hover:bg-green-900/30"
                      >
                        Get Art. 17 kit
                      </button>
                    )}
                    <button
                      onClick={() => handleDismiss(h.id)}
                      className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                    >
                      dismiss
                    </button>
                  </div>
                ))}
              </div>

              <div className="shrink-0">
                {arming === e.id ? (
                  <div className="flex flex-col gap-2 w-56">
                    <label className="text-xs text-gray-500 dark:text-gray-400">
                      {e.trigger_label}
                    </label>
                    <input
                      type="date"
                      value={triggerDate}
                      onChange={(ev) => setTriggerDate(ev.target.value)}
                      className="text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 dark:text-gray-100"
                    />
                    <input
                      type="text"
                      placeholder="Institution (e.g. Danske Bank)"
                      value={institution}
                      onChange={(ev) => setInstitution(ev.target.value)}
                      className="text-sm px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 dark:text-gray-100"
                    />
                    {e.expiry.conservative_years && (
                      <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300">
                        <input
                          type="checkbox"
                          checked={conservative}
                          onChange={(ev) => setConservative(ev.target.checked)}
                        />
                        Conservative ({e.expiry.conservative_years} years)
                      </label>
                    )}
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleArm(e.id)}
                        disabled={busy === e.id || !triggerDate}
                        className="flex-1 text-sm px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        Arm
                      </button>
                      <button
                        onClick={() => setArming("")}
                        className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setArming(e.id);
                      setTriggerDate("");
                      setInstitution("");
                      setConservative(false);
                    }}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700"
                  >
                    <Hourglass className="w-4 h-4" /> Arm a hold
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <h1 className="text-2xl font-bold mb-2 flex items-center gap-2">
        <ShieldOff className="w-6 h-6" /> Legally undeletable
      </h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-3xl">
        These sources cannot be erased — the law says so (Art. 17(3)). Here is
        what each one is, why it stays, and the restriction you CAN apply.
      </p>

      <div className="space-y-4">
        {restrictions.map((e) => (
          <div
            key={e.id}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5"
          >
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="font-semibold">{e.name}</h2>
              {e.requires_mitid && (
                <span className="flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-300">
                  <Fingerprint className="w-3 h-3" /> MitID
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{e.what_it_is}</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
              <span className="font-medium">Why it stays:</span> {e.why_undeletable}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">
              <span className="font-medium">What you can do:</span> {e.mitigation}
            </p>
            {e.mitigation_url && (
              <a
                href={e.mitigation_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-2 text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                <ExternalLink className="w-3.5 h-3.5" /> Open
              </a>
            )}
          </div>
        ))}
      </div>

      {kit && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-lg">Art. 17 — {kit.title}</h2>
              <button onClick={() => setKit(null)} aria-label="Close">
                <X className="w-5 h-5 text-gray-400 hover:text-gray-600" />
              </button>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">
              Send this to the institution's DPO from your own mailbox — the
              retention duty has matured, so cite it with confidence.
              {kit.escalationDays > 0 && (
                <> No substantive reply within {Math.round(kit.escalationDays / 30) || 1} month
                {(kit.escalationDays >= 60) ? "s" : ""} (Art. 12(3))? Escalate with a
                Datatilsynet complaint.</>
              )}
            </p>
            <textarea
              readOnly
              value={kit.text}
              className="w-full h-72 text-xs font-mono p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 text-gray-800 dark:text-gray-200"
            />
            <button
              onClick={() => {
                navigator.clipboard.writeText(kit.text);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="mt-3 flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700"
            >
              {copied ? <CheckCircle2 className="w-4 h-4" /> : <ClipboardCopy className="w-4 h-4" />}
              {copied ? "Copied" : "Copy text"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
