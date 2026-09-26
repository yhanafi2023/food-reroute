"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DemoState, Workspace } from "@/lib/types";
import { OfflineBanner } from "./States";

const WORKSPACE_LINKS: Record<Workspace, { href: string; label: string }[]> = {
  restaurant: [
    { href: "/restaurant", label: "Tonight" },
    { href: "/restaurant/surplus-log", label: "Surplus log" },
  ],
  volunteer: [{ href: "/volunteer", label: "Runs" }],
  org: [
    { href: "/org", label: "Deliveries" },
    { href: "/organization/onboarding", label: "Onboarding" },
  ],
  coordinator: [
    { href: "/coordinator", label: "Rescues" },
    { href: "/admin/prospects", label: "Prospects" },
  ],
};

const WORKSPACE_NAME: Record<Workspace, string> = {
  restaurant: "Restaurant",
  volunteer: "Volunteer",
  org: "Receiving organization",
  coordinator: "Coordinator",
};

type Theme = "light" | "dark";

function readTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function subscribeTheme(onChange: () => void) {
  const obs = new MutationObserver(onChange);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => obs.disconnect();
}

// Dark console is the default (238b63d); light is the viewer's choice and is remembered.
function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, readTheme, () => "dark" as Theme);
  const next: Theme = theme === "dark" ? "light" : "dark";
  const apply = () => {
    if (next === "light") document.documentElement.dataset.theme = "light";
    else delete document.documentElement.dataset.theme;
    try {
      if (next === "light") localStorage.setItem("foodflow_theme", "light");
      else localStorage.removeItem("foodflow_theme");
    } catch {
      // storage blocked: the choice lasts for this page only
    }
  };
  return (
    <button type="button" className="btn btn-ghost" onClick={apply} aria-label={`Switch to ${next} theme`}>
      {next === "light" ? "Light theme" : "Dark theme"}
    </button>
  );
}

// Logo mark from 238b63d: restaurant (amber) to organization (mint) along a live route (cyan/blue).
export function Brand() {
  return (
    <Link href="/" className="brand" aria-label="FoodFlow home">
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
        <circle cx="6" cy="21" r="4" fill="var(--m-restaurant)" />
        <circle cx="22" cy="7" r="4" fill="var(--m-org)" />
        <path d="M6 21 C 6 12, 22 16, 22 7" stroke="var(--cyan)" strokeWidth="3" fill="none" strokeLinecap="round" />
      </svg>
      FoodFlow
    </Link>
  );
}

// Demo clock and reset. Only renders when the server runs in demo mode.
export function DemoBar() {
  const [state, setState] = useState<DemoState | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const { user, logout } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";

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
      {isAdmin && state.demo_clock ? (
        <>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => act("/demo/clock", { action: state.running ? "pause" : "play" })}>
            {state.running ? "Pause" : "Play"}
          </button>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => act("/demo/clock", { action: "advance", minutes: 10 })}>
            Skip 10 min
          </button>
        </>
      ) : null}
      {isAdmin ? (
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
      ) : null}
      {note ? <span role="alert">{note}</span> : null}
    </div>
  );
}

export function Shell({ workspace, children }: { workspace?: Workspace; children: ReactNode }) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  return (
    <>
      <a href="#main" className="skip">
        Skip to content
      </a>
      <header className="topbar">
        <Brand />
        {workspace ? <span className="chip">{WORKSPACE_NAME[workspace]}</span> : null}
        {workspace && WORKSPACE_LINKS[workspace].length > 1 ? (
          <nav aria-label="Workspace" className="row" style={{ gap: "var(--s-1)" }}>
            {WORKSPACE_LINKS[workspace].map((l) => (
              <Link key={l.href} href={l.href} className="btn btn-ghost" aria-current={pathname === l.href ? "page" : undefined}>
                {l.label}
              </Link>
            ))}
          </nav>
        ) : null}
        <span style={{ flex: 1 }} />
        {user ? <span className="small muted hide-sm">Signed in as {user.name}</span> : null}
        <ThemeToggle />
        {user ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              logout();
              router.push("/demo");
            }}
          >
            Sign out
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
