import { useState } from "react";

interface UseSettingsSectionReturn<T> {
  status: T | null;
  setStatus: (s: T | null) => void;
  showForm: boolean;
  setShowForm: (show: boolean) => void;
  saving: boolean;
  message: { type: string; text: string };
  setMessage: (m: { type: string; text: string }) => void;
  withSaving: (fn: () => Promise<void>) => Promise<void>;
}

export function useSettingsSection<T>(): UseSettingsSectionReturn<T> {
  const [status, setStatus] = useState<T | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState({ type: "", text: "" });

  const withSaving = async (fn: () => Promise<void>) => {
    setSaving(true);
    setMessage({ type: "", text: "" });
    try {
      await fn();
    } catch (e) {
      setMessage({ type: "error", text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setSaving(false);
    }
  };

  return { status, setStatus, showForm, setShowForm, saving, message, setMessage, withSaving };
}
