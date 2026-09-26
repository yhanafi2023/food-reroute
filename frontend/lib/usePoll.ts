"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, isAbort } from "./api";

// Fetch `path` now and every `intervalMs` so dashboards update live without a refresh.
// - never overlaps requests; a new path or unmount cancels the one in flight
// - pauses while the tab is hidden and refreshes as soon as it is visible again
// - backs off (up to 30 s) while the server is unreachable, keeps the last good data
export function usePoll<T>(path: string | null, intervalMs = 3000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const inFlight = useRef<AbortController | null>(null);
  const failures = useRef(0);

  const refresh = useCallback(async () => {
    if (!path || inFlight.current) return;
    const ctrl = new AbortController();
    inFlight.current = ctrl;
    try {
      const next = await api<T>(path, { signal: ctrl.signal });
      setData(next);
      setError(null);
      setUpdatedAt(Date.now());
      failures.current = 0;
    } catch (e) {
      if (!isAbort(e)) {
        failures.current += 1;
        setError((e as Error).message);
      }
    } finally {
      if (inFlight.current === ctrl) inFlight.current = null;
    }
  }, [path]);

  useEffect(() => {
    if (!path) return;
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const loop = async () => {
      if (stopped) return;
      if (document.visibilityState === "visible") await refresh();
      const backoff = Math.min(intervalMs * 2 ** Math.min(failures.current, 4), 30000);
      timer = setTimeout(loop, failures.current ? backoff : intervalMs);
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    timer = setTimeout(loop, 0);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      inFlight.current?.abort();
      inFlight.current = null;
    };
  }, [path, intervalMs, refresh]);

  const reload = useCallback(async () => {
    inFlight.current?.abort();
    inFlight.current = null;
    await refresh();
  }, [refresh]);

  return { data, error, updatedAt, refresh: reload };
}
