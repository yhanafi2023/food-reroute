"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";

const SEND_EVERY_MS = 10000;

// Shares the driver's phone GPS with FoodFlow while `enabled`. Sends at most every 10 s.
export function useShareLocation(enabled: boolean) {
  const [status, setStatus] = useState<{ state: "off" | "waiting" | "sharing" | "error"; message?: string; sentAt?: number }>({ state: "off" });
  const lastSent = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    if (!("geolocation" in navigator)) {
      queueMicrotask(() => setStatus({ state: "error", message: "This browser cannot share location." }));
      return;
    }
    queueMicrotask(() => setStatus({ state: "waiting", message: "Waiting for GPS..." }));
    const ctrl = new AbortController();
    const id = navigator.geolocation.watchPosition(
      async (pos) => {
        const now = Date.now();
        if (now - lastSent.current < SEND_EVERY_MS) return;
        lastSent.current = now;
        try {
          await api("/volunteers/me/location", {
            method: "PATCH",
            body: { lat: pos.coords.latitude, lng: pos.coords.longitude },
            signal: ctrl.signal,
          });
          setStatus({ state: "sharing", sentAt: now });
        } catch (e) {
          if (!ctrl.signal.aborted) setStatus({ state: "error", message: (e as Error).message });
        }
      },
      (err) => setStatus({ state: "error", message: err.code === err.PERMISSION_DENIED ? "Location permission was denied. FoodFlow will estimate your position from the route." : "GPS is unavailable right now." }),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 },
    );
    return () => {
      navigator.geolocation.clearWatch(id);
      ctrl.abort();
      setStatus({ state: "off" });
    };
  }, [enabled]);

  return status;
}
