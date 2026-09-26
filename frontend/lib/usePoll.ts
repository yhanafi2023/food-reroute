"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

// Fetch `path` now and every `intervalMs` (3 seconds by default) so dashboards update live.
export function usePoll<T>(path: string | null, intervalMs = 3000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    if (!path) return;
    try {
      const next = await api<T>(path);
      if (alive.current) {
        setData(next);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    if (!path) return;
    const first = setTimeout(refresh, 0);
    const id = setInterval(refresh, intervalMs);
    return () => {
      alive.current = false;
      clearTimeout(first);
      clearInterval(id);
    };
  }, [path, intervalMs, refresh]);

  return { data, error, refresh };
}
