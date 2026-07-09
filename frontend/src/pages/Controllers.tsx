import { useEffect, useState } from "react";
import { api } from "../api/client";
import Modal from "../components/Modal";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCopy,
  ExternalLink,
  Loader2,
  Mail,
  ScrollText,
} from "lucide-react";

interface ControllerRequest {
  id: string;
  status: string;
  sent_at: string | null;
  deadline_at: string | null;
  created_at: string | null;
}

interface Controller {
  id: string;
  name: string;
  domain: string;
  eu_entity: string;
  entity_country: string;
  lead_dpa: string;
  no_eu_establishment: boolean;
  contact_kind: string;
  privacy_email: string;
  email_viable: boolean;
  selfservice_url: string;
  erasure_form_url: string;
  retention_note: string;
  art17_value: string;
  special_category: boolean;
  send_from_account_email: boolean;
  prerequisites: string[];
  form_instructions: string;
  postal_address: string;
  request: ControllerRequest | null;
}

interface Kit {
  request_text: string;
  form_url: string | null;
  form_instructions: string;
  prerequisites: string[];
  selfservice_url: string;
  postal_address: string;
  send_from_account_email: boolean;
}

const statusStyles: Record<string, string> = {
  created: "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200",
  manual_action_needed: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  sent: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  acknowledged: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200",
  completed: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  refused: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  overdue: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  escalated: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
};

const statusLabels: Record<string, string> = {
  created: "Created",
  manual_action_needed: "File the kit",
  sent: "Sent — clock running",
  acknowledged: "Acknowledged",
  completed: "Completed",
  refused: "Refused",
  overdue: "Overdue",
  escalated: "Escalated",
};

export default function Controllers() {
  const [controllers, setControllers] = useState<Controller[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [kit, setKit] = useState<{ controller: Controller; kit: Kit; requestId: string } | null>(null);
  const [copied, setCopied] = useState(false);

  async function load() {
    try {
      const data = await api.getControllers();
      setControllers(data as unknown as Controller[]);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load controllers");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleStart(c: Controller) {
    setBusy(c.id);
    try {
      const resp = await api.createControllerRequest(c.id);
      if (resp.status === "manual_action_needed") {
        setKit({ controller: c, kit: resp.kit as unknown as Kit, requestId: resp.request_id });
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create request");
    } finally {
      setBusy("");
    }
  }

  async function handleViewKit(c: Controller) {
    setBusy(c.id);
    try {
      const resp = await api.getControllerKit(c.id);
      setKit({ controller: c, kit: resp.kit as unknown as Kit, requestId: resp.request_id });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load kit");
    } finally {
      setBusy("");
    }
  }

  async function handleMarkFiled(requestId: string, controllerId: string) {
    setBusy(controllerId);
    try {
      await api.transitionRequest(requestId, "mark_sent");
      setKit(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to mark as filed");
    } finally {
      setBusy("");
    }
  }

  async function copyKitText() {
    if (!kit) return;
    await navigator.clipboard.writeText(kit.kit.request_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
      <h1 className="text-2xl font-bold mb-2">Controllers</h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-3xl">
        Tech giants you may have an account with. Erasure here means account deletion, so
        every request is opt-in per platform — run the self-service deletion first, then
        file the formal Art. 17 for what survives it. Platforms without a verified privacy
        email get a kit to paste into their rights form; the 30-day clock starts when you
        confirm you filed it.
      </p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg text-sm">
          {error}
        </div>
      )}

      <div className="space-y-4">
        {controllers.map((c) => (
          <div
            key={c.id}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="font-semibold">{c.name}</h2>
                  {c.request ? (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusStyles[c.request.status] || statusStyles.created}`}
                    >
                      {statusLabels[c.request.status] || c.request.status}
                    </span>
                  ) : (
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                      Not started
                    </span>
                  )}
                  {c.email_viable ? (
                    <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-300">
                      <Mail className="w-3 h-3" /> email
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-300">
                      <ScrollText className="w-3 h-3" /> form only
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  {c.eu_entity}
                  {c.no_eu_establishment
                    ? " — no EU establishment; your DPA has direct competence"
                    : ` — lead SA: ${c.lead_dpa}`}
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">
                  <span className="font-medium">Survives account deletion:</span> {c.retention_note}
                </p>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
                  <span className="font-medium">What Art. 17 adds:</span> {c.art17_value}
                </p>
                {c.prerequisites.length > 0 && (
                  <ul className="mt-2 space-y-0.5">
                    {c.prerequisites.map((p) => (
                      <li key={p} className="text-xs text-gray-500 dark:text-gray-400 flex items-start gap-1">
                        <CheckCircle2 className="w-3 h-3 mt-0.5 shrink-0" /> {p}
                      </li>
                    ))}
                  </ul>
                )}
                {c.request?.deadline_at && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                    Art. 12(3) deadline: {c.request.deadline_at.slice(0, 10)}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-2 shrink-0">
                <a
                  href={c.selfservice_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <ExternalLink className="w-4 h-4" /> Self-service deletion
                </a>
                {!c.request ||
                c.request.status === "completed" ||
                c.request.status === "created" ? (
                  <button
                    onClick={() => handleStart(c)}
                    disabled={busy === c.id}
                    className="flex items-center justify-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {busy === c.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : c.email_viable ? (
                      <Mail className="w-4 h-4" />
                    ) : (
                      <ScrollText className="w-4 h-4" />
                    )}
                    {c.request?.status === "created"
                      ? "Retry send"
                      : c.email_viable
                        ? "Send Art. 17 email"
                        : "Generate filing kit"}
                  </button>
                ) : c.request.status === "manual_action_needed" ? (
                  <>
                    <button
                      onClick={() => handleViewKit(c)}
                      disabled={busy === c.id}
                      className="flex items-center justify-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      <ScrollText className="w-4 h-4" /> View kit
                    </button>
                    <button
                      onClick={() => c.request && handleMarkFiled(c.request.id, c.id)}
                      disabled={busy === c.id}
                      className="flex items-center justify-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-green-600 text-green-700 dark:text-green-300 hover:bg-green-50 dark:hover:bg-green-900/30 disabled:opacity-50"
                    >
                      <CheckCircle2 className="w-4 h-4" /> I filed it
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>

      {kit && (
        <Modal title={`Filing kit — ${kit.controller.name}`} onClose={() => setKit(null)}>
            {kit.kit.send_from_account_email && (
              <div className="mb-3 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 text-sm flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                Must be sent from the email address verified on your account — requests
                from other addresses are rejected.
              </div>
            )}

            <ol className="text-sm text-gray-600 dark:text-gray-300 mb-3 list-decimal list-inside space-y-1">
              <li>Copy the request text below.</li>
              <li>
                {kit.kit.form_url ? (
                  <>
                    Open the{" "}
                    <a
                      href={kit.kit.form_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-600 dark:text-indigo-400 underline"
                    >
                      rights form
                    </a>{" "}
                    and paste it.
                  </>
                ) : (
                  "Paste it into the platform's privacy contact channel."
                )}
              </li>
              <li>Come back and press "I filed it" — that starts the 30-day clock.</li>
            </ol>
            {kit.kit.form_instructions && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                {kit.kit.form_instructions}
              </p>
            )}

            <textarea
              readOnly
              value={kit.kit.request_text}
              className="w-full h-64 text-xs font-mono p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900 text-gray-800 dark:text-gray-200"
            />

            <div className="flex items-center gap-2 mt-4">
              <button
                onClick={copyKitText}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700"
              >
                <ClipboardCopy className="w-4 h-4" /> {copied ? "Copied" : "Copy text"}
              </button>
              <button
                onClick={() => handleMarkFiled(kit.requestId, kit.controller.id)}
                disabled={busy === kit.controller.id}
                className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border border-green-600 text-green-700 dark:text-green-300 hover:bg-green-50 dark:hover:bg-green-900/30 disabled:opacity-50"
              >
                <CheckCircle2 className="w-4 h-4" /> I filed it
              </button>
              {kit.kit.postal_address && (
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
                  Postal fallback: {kit.kit.postal_address}
                </span>
              )}
            </div>
        </Modal>
      )}
    </div>
  );
}
