import { useEffect, useRef, useState } from "react";

interface TaskState<T> {
  running: boolean;
  progress: number;
  total: number;
  error: string;
  results: T | null;
  hasResults: boolean;
  runningLabel: string;
}

interface UseAsyncTaskOptions<T> {
  startFn: (...args: unknown[]) => Promise<{ status: string; [key: string]: unknown }>;
  statusFn: () => Promise<{ running: boolean; progress?: number; total?: number; error?: string | null; email?: string }>;
  resultsFn: () => Promise<T & { has_results: boolean }>;
  pollInterval?: number;
}

export function useAsyncTask<T>({ startFn, statusFn, resultsFn, pollInterval = 2000 }: UseAsyncTaskOptions<T>) {
  const [state, setState] = useState<TaskState<T>>({
    running: false,
    progress: 0,
    total: 0,
    error: "",
    results: null,
    hasResults: false,
    runningLabel: "",
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function loadResults() {
    try {
      const data = await resultsFn();
      if (!mountedRef.current) return;
      setState((prev) => ({
        ...prev,
        results: data,
        hasResults: data.has_results,
      }));
    } catch {
      // No results yet
    }
  }

  function startPolling() {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const status = await statusFn();
        if (!mountedRef.current) return;
        setState((prev) => ({
          ...prev,
          progress: status.progress ?? prev.progress,
          total: status.total ?? prev.total,
          runningLabel: status.email ?? prev.runningLabel,
        }));
        if (status.error) {
          setState((prev) => ({ ...prev, error: status.error!, running: false }));
          stopPolling();
          return;
        }
        if (!status.running) {
          setState((prev) => ({ ...prev, running: false }));
          stopPolling();
          await loadResults();
        }
      } catch {
        // ignore poll errors
      }
    }, pollInterval);
  }

  async function checkIfRunning() {
    try {
      const status = await statusFn();
      if (status.running) {
        setState((prev) => ({
          ...prev,
          running: true,
          progress: status.progress ?? 0,
          total: status.total ?? 0,
        }));
        startPolling();
      }
    } catch {
      // ignore
    }
  }

  async function start(...args: unknown[]) {
    setState((prev) => ({ ...prev, running: true, error: "", progress: 0, results: null, hasResults: false, runningLabel: "" }));
    try {
      const data = await startFn(...args);
      const dataObj = data as Record<string, unknown>;
      setState((prev) => ({
        ...prev,
        total: (dataObj.total as number | undefined) ?? prev.total,
        runningLabel: (dataObj.email as string | undefined) ?? prev.runningLabel,
      }));
      startPolling();
      return data;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Task failed";
      setState((prev) => ({ ...prev, error: msg, running: false }));
      throw e;
    }
  }

  useEffect(() => {
    mountedRef.current = true;
    loadResults();
    checkIfRunning();
    return () => {
      mountedRef.current = false;
      stopPolling();
    };
  }, []);

  return { ...state, start, loadResults };
}
