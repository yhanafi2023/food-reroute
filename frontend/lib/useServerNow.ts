"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

// The server's clock (the demo clock in demo mode). Deadlines and "in 12 min" use this, not the device clock.
let offsetMs = 0;
let synced = false;

export async function syncServerTime(): Promise<void> {
  const t0 = Date.now();
  const res = await api<{ now: string }>("/time");
  offsetMs = new Date(res.now).getTime() - (t0 + Date.now()) / 2;
  synced = true;
}

export function serverNowMs(): number {
  return Date.now() + offsetMs;
}

export function useServerNow(tickMs = 1000): string | null {
  const [now, setNow] = useState<string | null>(synced ? new Date(serverNowMs()).toISOString() : null);
  useEffect(() => {
    let stopped = false;
    const sync = () => syncServerTime().then(() => !stopped && setNow(new Date(serverNowMs()).toISOString())).catch(() => {});
    sync();
    const syncTimer = setInterval(sync, 10000);
    const tick = setInterval(() => synced && setNow(new Date(serverNowMs()).toISOString()), tickMs);
    return () => {
      stopped = true;
      clearInterval(syncTimer);
      clearInterval(tick);
    };
  }, [tickMs]);
  return now;
}
