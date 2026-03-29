import { useEffect, useRef, useState } from "react";

interface TaskState<T> {
  running: boolean;
  progress: number;
  total: number;
  error: string;
  results: T | null;
  hasResults: boolean;
}

interface UseAsyncTaskOptions<T> {
  startFn: (...args: unknown[]) => Promise<{ status: string; [key: string]: unknown }>;
  statusFn: () => Promise<{ running: boolean; progress?: number; total?: number; error?: string | null }>;
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
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function loadResults() {
    try {
      const data = await resultsFn();
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
        setState((prev) => ({
          ...prev,
          progress: status.progress ?? prev.progress,
          total: status.total ?? prev.total,
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
    setState((prev) => ({ ...prev, running: true, error: "", progress: 0 }));
    try {
      const data = await startFn(...args);
      setState((prev) => ({
        ...prev,
        total: (data as Record<string, unknown>).total as number ?? prev.total,
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
    loadResults();
    checkIfRunning();
    return stopPolling;
  }, []);

  return { ...state, start, loadResults };
}
