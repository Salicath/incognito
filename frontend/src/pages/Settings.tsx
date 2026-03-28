import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { Mail, User, Info, CheckCircle, Loader2, ShieldAlert, Download, Upload } from "lucide-react";

const BASE = "/api";

async function settingsRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const message = typeof body.detail === "string" ? body.detail : res.statusText;
    throw new Error(message);
  }
  return res.json();
}

interface SmtpStatus {
  configured: boolean;
  host?: string;
  port?: number;
  username?: string;
}

interface HibpStatus {
  configured: boolean;
  key_preview?: string;
}

interface AppInfo {
  broker_count: number;
  data_dir: string;
  version: string;
}

export default function Settings() {
  const [smtpStatus, setSmtpStatus] = useState<SmtpStatus | null>(null);
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);

  const [smtpForm, setSmtpForm] = useState({ host: "", port: 587, username: "", password: "" });
  const [showSmtpForm, setShowSmtpForm] = useState(false);
  const [smtpSaving, setSmtpSaving] = useState(false);
  const [smtpTesting, setSmtpTesting] = useState(false);
  const [smtpMessage, setSmtpMessage] = useState({ type: "", text: "" });

  // HIBP state
  const [hibpStatus, setHibpStatus] = useState<HibpStatus | null>(null);
  const [hibpKeyInput, setHibpKeyInput] = useState("");
  const [showHibpForm, setShowHibpForm] = useState(false);
  const [hibpSaving, setHibpSaving] = useState(false);
  const [hibpDeleting, setHibpDeleting] = useState(false);
  const [hibpMessage, setHibpMessage] = useState({ type: "", text: "" });

  // Backup state
  const [backupExporting, setBackupExporting] = useState(false);
  const [backupImporting, setBackupImporting] = useState(false);
  const [backupMessage, setBackupMessage] = useState({ type: "", text: "" });
  const importFileRef = useRef<HTMLInputElement>(null);

  // Profile editing state
  const [editingProfile, setEditingProfile] = useState(false);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editDob, setEditDob] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState({ type: "", text: "" });

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [smtp, info, prof, hibp] = await Promise.all([
        settingsRequest<SmtpStatus>("/settings/smtp"),
        settingsRequest<AppInfo>("/settings/info"),
        api.getProfile(),
        api.getHibpStatus(),
      ]);
      setSmtpStatus(smtp);
      setAppInfo(info);
      setProfile(prof);
      setHibpStatus(hibp);
      // Populate profile edit fields with current values
      setEditName((prof.full_name as string) || "");
      setEditEmail(((prof.emails as string[]) || [])[0] || "");
      setEditPhone(((prof.phones as string[]) || [])[0] || "");
      setEditDob((prof.date_of_birth as string) || "");
      if (smtp.configured) {
        setSmtpForm({ host: smtp.host || "", port: smtp.port || 587, username: smtp.username || "", password: "" });
      }
    } catch {
      // ignore
    }
  }

  async function handleSaveHibpKey() {
    setHibpSaving(true);
    setHibpMessage({ type: "", text: "" });
    try {
      await api.saveHibpKey(hibpKeyInput.trim());
      setHibpMessage({ type: "success", text: "API key saved." });
      setShowHibpForm(false);
      setHibpKeyInput("");
      loadData();
    } catch (e) {
      setHibpMessage({ type: "error", text: e instanceof Error ? e.message : "Failed to save" });
    } finally {
      setHibpSaving(false);
    }
  }

  async function handleDeleteHibpKey() {
    setHibpDeleting(true);
    setHibpMessage({ type: "", text: "" });
    try {
      await api.deleteHibpKey();
      setHibpMessage({ type: "success", text: "API key removed." });
      loadData();
    } catch (e) {
      setHibpMessage({ type: "error", text: e instanceof Error ? e.message : "Failed to delete" });
    } finally {
      setHibpDeleting(false);
    }
  }

  async function handleSaveSmtp() {
    setSmtpSaving(true);
    setSmtpMessage({ type: "", text: "" });
    try {
      await settingsRequest("/settings/smtp", {
        method: "POST",
        body: JSON.stringify({ smtp: smtpForm }),
      });
      setSmtpMessage({ type: "success", text: "SMTP settings saved." });
      setShowSmtpForm(false);
      loadData();
    } catch (e) {
      setSmtpMessage({ type: "error", text: e instanceof Error ? e.message : "Failed to save" });
    } finally {
      setSmtpSaving(false);
    }
  }

  async function handleTestSmtp() {
    setSmtpTesting(true);
    setSmtpMessage({ type: "", text: "" });
    try {
      const result = await settingsRequest<{ message: string }>("/settings/test-smtp", { method: "POST" });
      setSmtpMessage({ type: "success", text: result.message });
    } catch (e) {
      setSmtpMessage({ type: "error", text: e instanceof Error ? e.message : "Test failed" });
    } finally {
      setSmtpTesting(false);
    }
  }

  async function handleSaveProfile() {
    setProfileSaving(true);
    setProfileMessage({ type: "", text: "" });
    try {
      await settingsRequest("/settings/profile", {
        method: "POST",
        body: JSON.stringify({
          profile: {
            full_name: editName,
            emails: [editEmail].filter((e) => e.trim()),
            phones: [editPhone].filter((p) => p.trim()),
            date_of_birth: editDob || undefined,
          },
        }),
      });
      setProfileMessage({ type: "success", text: "Profile saved." });
      setEditingProfile(false);
      loadData();
    } catch (e) {
      setProfileMessage({ type: "error", text: e instanceof Error ? e.message : "Failed to save" });
    } finally {
      setProfileSaving(false);
    }
  }

  async function handleExport() {
    setBackupExporting(true);
    setBackupMessage({ type: "", text: "" });
    try {
      const res = await fetch("/api/settings/backup/export", { credentials: "include" });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "incognito-backup.json";
      a.click();
      URL.revokeObjectURL(url);
      setBackupMessage({ type: "success", text: "Backup exported successfully." });
    } catch (e) {
      setBackupMessage({ type: "error", text: e instanceof Error ? e.message : "Export failed" });
    } finally {
      setBackupExporting(false);
    }
  }

  async function handleImport(file: File) {
    setBackupImporting(true);
    setBackupMessage({ type: "", text: "" });
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const res = await fetch("/api/settings/backup/import", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(typeof body.detail === "string" ? body.detail : res.statusText);
      }
      const result = await res.json();
      setBackupMessage({ type: "success", text: result.message || "Backup imported successfully." });
    } catch (e) {
      setBackupMessage({ type: "error", text: e instanceof Error ? e.message : "Import failed" });
    } finally {
      setBackupImporting(false);
      if (importFileRef.current) importFileRef.current.value = "";
    }
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm";

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      {/* SMTP Configuration */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 mb-6">
        <div className="px-5 py-4 border-b border-gray-200 flex items-center gap-2">
          <Mail className="w-4 h-4 text-gray-500" />
          <h2 className="font-semibold">Email (SMTP)</h2>
        </div>
        <div className="p-5">
          {smtpStatus && !smtpStatus.configured && !showSmtpForm && (
            <div>
              <p className="text-sm text-gray-600 mb-3">
                SMTP is required to send GDPR requests via email. Configure your email provider's SMTP settings.
              </p>
              <button onClick={() => setShowSmtpForm(true)}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition">
                Configure SMTP
              </button>
            </div>
          )}

          {smtpStatus && smtpStatus.configured && !showSmtpForm && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span className="text-sm text-green-700 font-medium">SMTP configured</span>
              </div>
              <div className="text-sm text-gray-600 space-y-1 mb-4">
                <p><span className="font-medium">Server:</span> {smtpStatus.host}:{smtpStatus.port}</p>
                <p><span className="font-medium">Username:</span> {smtpStatus.username}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setShowSmtpForm(true)}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition">
                  Update
                </button>
                <button onClick={handleTestSmtp} disabled={smtpTesting}
                  className="flex items-center gap-1 px-3 py-1.5 text-sm bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition disabled:opacity-50">
                  {smtpTesting ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                  Send test email
                </button>
              </div>
            </div>
          )}

          {showSmtpForm && (
            <div className="space-y-3">
              <input type="text" placeholder="SMTP server (e.g. smtp.protonmail.ch)" value={smtpForm.host}
                onChange={(e) => setSmtpForm({ ...smtpForm, host: e.target.value })} className={inputClass} />
              <input type="number" placeholder="Port (587)" value={smtpForm.port}
                onChange={(e) => setSmtpForm({ ...smtpForm, port: parseInt(e.target.value) || 587 })} className={inputClass} />
              <input type="text" placeholder="Username (email)" value={smtpForm.username}
                onChange={(e) => setSmtpForm({ ...smtpForm, username: e.target.value })} className={inputClass} />
              <input type="password" placeholder="Password / App password" value={smtpForm.password}
                onChange={(e) => setSmtpForm({ ...smtpForm, password: e.target.value })} className={inputClass} />
              <div className="flex gap-2">
                <button onClick={handleSaveSmtp} disabled={smtpSaving}
                  className="flex items-center gap-1 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition disabled:opacity-50">
                  {smtpSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                  Save
                </button>
                <button onClick={() => { setShowSmtpForm(false); setSmtpMessage({ type: "", text: "" }); }}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 transition">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {smtpMessage.text && (
            <div className={`mt-3 px-3 py-2 rounded-lg text-sm ${smtpMessage.type === "success" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              {smtpMessage.text}
            </div>
          )}
        </div>
      </div>

      {/* Have I Been Pwned API Key */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 mb-6">
        <div className="px-5 py-4 border-b border-gray-200 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-gray-500" />
          <h2 className="font-semibold">Have I Been Pwned (HIBP)</h2>
        </div>
        <div className="p-5">
          {hibpStatus && !hibpStatus.configured && !showHibpForm && (
            <div>
              <p className="text-sm text-gray-600 mb-3">
                Optional: enter a{" "}
                <a href="https://haveibeenpwned.com/API/Key" target="_blank" rel="noopener noreferrer"
                  className="text-indigo-600 underline hover:text-indigo-800">
                  Have I Been Pwned API key
                </a>{" "}
                to check whether your email has appeared in known data breaches.
              </p>
              <button onClick={() => setShowHibpForm(true)}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition">
                Add API Key
              </button>
            </div>
          )}

          {hibpStatus && hibpStatus.configured && !showHibpForm && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle className="w-4 h-4 text-green-500" />
                <span className="text-sm text-green-700 font-medium">HIBP API key configured</span>
              </div>
              <div className="text-sm text-gray-600 mb-4">
                <p><span className="font-medium">Key:</span> {hibpStatus.key_preview}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setShowHibpForm(true)}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition">
                  Update
                </button>
                <button onClick={handleDeleteHibpKey} disabled={hibpDeleting}
                  className="flex items-center gap-1 px-3 py-1.5 text-sm bg-red-50 text-red-700 rounded-lg hover:bg-red-100 transition disabled:opacity-50">
                  {hibpDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                  Remove Key
                </button>
              </div>
            </div>
          )}

          {showHibpForm && (
            <div className="space-y-3">
              <input
                type="password"
                placeholder="Paste your HIBP API key here"
                value={hibpKeyInput}
                onChange={(e) => setHibpKeyInput(e.target.value)}
                className={inputClass}
              />
              <p className="text-xs text-gray-500">
                Get a key at{" "}
                <a href="https://haveibeenpwned.com/API/Key" target="_blank" rel="noopener noreferrer"
                  className="text-indigo-600 underline">
                  haveibeenpwned.com/API/Key
                </a>. The key is stored in plain text in your data directory.
              </p>
              <div className="flex gap-2">
                <button onClick={handleSaveHibpKey} disabled={hibpSaving || !hibpKeyInput.trim()}
                  className="flex items-center gap-1 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition disabled:opacity-50">
                  {hibpSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                  Save
                </button>
                <button onClick={() => { setShowHibpForm(false); setHibpKeyInput(""); setHibpMessage({ type: "", text: "" }); }}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 transition">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {hibpMessage.text && (
            <div className={`mt-3 px-3 py-2 rounded-lg text-sm ${hibpMessage.type === "success" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              {hibpMessage.text}
            </div>
          )}
        </div>
      </div>

      {/* Profile Info */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 mb-6">
        <div className="px-5 py-4 border-b border-gray-200 flex items-center gap-2">
          <User className="w-4 h-4 text-gray-500" />
          <h2 className="font-semibold">Profile</h2>
        </div>
        <div className="p-5">
          {profile ? (
            editingProfile ? (
              <div className="space-y-3">
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="Full name"
                  className={inputClass}
                />
                <input
                  type="email"
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  placeholder="Primary email"
                  className={inputClass}
                />
                <input
                  type="tel"
                  value={editPhone}
                  onChange={(e) => setEditPhone(e.target.value)}
                  placeholder="Phone (optional)"
                  className={inputClass}
                />
                <input
                  type="date"
                  value={editDob}
                  onChange={(e) => setEditDob(e.target.value)}
                  className={inputClass}
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleSaveProfile}
                    disabled={profileSaving}
                    className="flex items-center gap-1 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition disabled:opacity-50"
                  >
                    {profileSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                    Save
                  </button>
                  <button
                    onClick={() => { setEditingProfile(false); setProfileMessage({ type: "", text: "" }); }}
                    className="px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 transition"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <div className="text-sm text-gray-600 space-y-1 mb-4">
                  <p><span className="font-medium">Name:</span> {profile.full_name as string}</p>
                  <p><span className="font-medium">Email:</span> {(profile.emails as string[])?.join(", ")}</p>
                  {profile.date_of_birth != null && <p><span className="font-medium">DOB:</span> {String(profile.date_of_birth)}</p>}
                  {(profile.phones as string[])?.length > 0 && (profile.phones as string[])[0] && (
                    <p><span className="font-medium">Phone:</span> {(profile.phones as string[]).join(", ")}</p>
                  )}
                </div>
                <button
                  onClick={() => setEditingProfile(true)}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition"
                >
                  Edit
                </button>
              </div>
            )
          ) : (
            <p className="text-sm text-gray-500">Loading...</p>
          )}

          {profileMessage.text && (
            <div className={`mt-3 px-3 py-2 rounded-lg text-sm ${profileMessage.type === "success" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              {profileMessage.text}
            </div>
          )}
        </div>
      </div>

      {/* App Info */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 mb-6">
        <div className="px-5 py-4 border-b border-gray-200 flex items-center gap-2">
          <Info className="w-4 h-4 text-gray-500" />
          <h2 className="font-semibold">About</h2>
        </div>
        <div className="p-5">
          {appInfo ? (
            <div className="text-sm text-gray-600 space-y-1">
              <p><span className="font-medium">Version:</span> {appInfo.version}</p>
              <p><span className="font-medium">Brokers:</span> {appInfo.broker_count} in registry</p>
              <p><span className="font-medium">Data:</span> {appInfo.data_dir}</p>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Loading...</p>
          )}
        </div>
      </div>

      {/* Backup */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="px-5 py-4 border-b border-gray-200 flex items-center gap-2">
          <Download className="w-4 h-4 text-gray-500" />
          <h2 className="font-semibold">Backup</h2>
        </div>
        <div className="p-5">
          <p className="text-sm text-gray-600 mb-4">
            Export an encrypted backup of your vault, database, and settings. Import it to restore your data on a new device.
          </p>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={handleExport}
              disabled={backupExporting}
              className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition disabled:opacity-50"
            >
              {backupExporting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
              Export Backup
            </button>
            <button
              onClick={() => importFileRef.current?.click()}
              disabled={backupImporting}
              className="flex items-center gap-1.5 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium hover:bg-gray-50 transition disabled:opacity-50"
            >
              {backupImporting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
              Import Backup
            </button>
            <input
              ref={importFileRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleImport(file);
              }}
            />
          </div>
          {backupMessage.text && (
            <div className={`mt-3 px-3 py-2 rounded-lg text-sm ${backupMessage.type === "success" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              {backupMessage.text}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
