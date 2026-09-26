"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DemoState, Workspace } from "@/lib/types";
import { OfflineBanner } from "./States";

const WORKSPACE_NAME: Record<Workspace, string> = {
  restaurant: "Restaurant",
  volunteer: "Volunteer",
  org: "Receiving organization",
  coordinator: "Coordinator",
};

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | "system">("system");
  useEffect(() => {
    const t = document.documentElement.dataset.theme;
    setTheme(t === "light" || t === "dark" ? t : "system");
  }, []);
  const next = theme === "system" ? "dark" : theme === "dark" ? "light" : "system";
  const apply = () => {
    if (next === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try {
      if (next === "system") localStorage.removeItem("foodflow_theme");
      else localStorage.setItem("foodflow_theme", next);
    } catch {
      // storage blocked: the choice lasts for this page only
    }
    setTheme(next);
  };
  return (
    <button type="button" className="btn btn-ghost" onClick={apply} aria-label={`Theme: ${theme}. Switch to ${next}`}>
      Theme: {theme}
    </button>
  );
}

// Demo clock and reset. Only renders when the server runs in demo mode.
export function DemoBar() {
  const [state, setState] = useState<DemoState | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const { logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    let stopped = false;
    const load = () =>
      api<DemoState>("/demo/state")
        .then((s) => !stopped && setState(s))
        .catch(() => !stopped && setState(null));
    load();
    const t = setInterval(load, 5000);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, []);
  if (!state) return null;

  const act = async (path: string, body?: unknown) => {
    setBusy(true);
    setNote("");
    try {
      const s = await api<DemoState>(path, { method: "POST", body });
      setState(s);
      return s;
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "The demo control failed");
      return null;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="demobar" role="region" aria-label="Demo controls">
      <span className="chip chip-warn">Fictional demo data</span>
      <span>
        Demo clock: <strong data-testid="demo-clock">{state.local_time}</strong> {state.running ? "" : "(paused)"}
      </span>
      {state.demo_clock ? (
        <>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => act("/demo/clock", { action: state.running ? "pause" : "play" })}>
            {state.running ? "Pause" : "Play"}
          </button>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => act("/demo/clock", { action: "advance", minutes: 10 })}>
            Skip 10 min
          </button>
        </>
      ) : null}
      <button
        type="button"
        className="btn btn-ghost"
        disabled={busy}
        onClick={async () => {
          if (await act("/demo/reset")) {
            logout();
            router.push("/demo");
          }
        }}
      >
        Reset demo
      </button>
      {note ? <span role="alert">{note}</span> : null}
    </div>
  );
}

export function Shell({ workspace, children }: { workspace?: Workspace; children: ReactNode }) {
  const { user, logout } = useAuth();
  const router = useRouter();
  return (
    <>
      <a href="#main" className="skip">
        Skip to content
      </a>
      <header className="topbar">
        <Link href="/" className="brand">
          FoodFlow
        </Link>
        {workspace ? <span className="chip">{WORKSPACE_NAME[workspace]}</span> : null}
        <span style={{ flex: 1 }} />
        {user ? <span className="small muted">Signed in as {user.name}</span> : null}
        <ThemeToggle />
        {user ? (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              logout();
              router.push("/demo");
            }}
          >
            Switch role
          </button>
        ) : null}
      </header>
      <DemoBar />
      <OfflineBanner />
      <main id="main" className="page">
        {children}
      </main>
    </>
  );
}
