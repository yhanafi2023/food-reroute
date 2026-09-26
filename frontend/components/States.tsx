"use client";
import { useEffect, useState } from "react";

export function Loading({ label, what, rows = 2 }: { label?: string; what?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="stack">
      <span className="sr-only">{label ?? (what ? `Loading ${what}` : "Loading")}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: 88 }} />
      ))}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="panel stack" style={{ borderStyle: "dashed" }}>
      <strong>{title}</strong>
      {children ? <div className="muted small">{children}</div> : null}
    </div>
  );
}

// `stale`: the page still shows the last good data, so say so instead of implying it is gone.
export function ErrorNote({ message, onRetry, stale = false }: { message: string | null | undefined; onRetry?: () => void; stale?: boolean }) {
  if (!message) return null;
  return (
    <div role="alert" className="alert alert-bad row" style={{ justifyContent: "space-between" }}>
      <span>
        {message}
        {stale ? " Showing the last information FoodFlow had." : ""}
      </span>
      {onRetry ? (
        <button type="button" className="btn btn-ghost" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

// Shown while the device reports no connection; pages keep their last data and retry on their own.
export function OfflineBanner() {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  if (!offline) return null;
  return (
    <div role="status" className="alert alert-info" style={{ borderRadius: 0 }}>
      You are offline. FoodFlow is showing the last information it had and will update when you reconnect.
    </div>
  );
}
