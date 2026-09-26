"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";

export function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2 no-underline" aria-label="FoodFlow home">
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden>
        <circle cx="6" cy="21" r="4" fill="#e0701c" />
        <circle cx="22" cy="7" r="4" fill="#14734a" />
        <path d="M6 21 C 6 12, 22 16, 22 7" stroke="#1456d9" strokeWidth="3" fill="none" strokeLinecap="round" />
      </svg>
      <span className="text-xl font-bold tracking-tight text-ink" style={{ fontFamily: "var(--ff-display)" }}>FoodFlow</span>
    </Link>
  );
}

export default function AppShell({ title, subtitle, children, actions }: {
  title: string; subtitle?: string; children: ReactNode; actions?: ReactNode;
}) {
  const { user, logout } = useAuth();
  const router = useRouter();
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <Brand />
          <div className="flex items-center gap-3">
            {user && (
              <span className="hidden text-sm text-ink-2 sm:inline">
                <span className="eyebrow mr-2">{user.role.toLowerCase()}</span>
                {user.name}
              </span>
            )}
            <Link href="/impact" className="btn btn-ghost">Impact</Link>
            {user && <button className="btn btn-ghost" onClick={() => { logout(); router.push("/login"); }}>Log out</button>}
          </div>
        </div>
      </header>
      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 style={{ fontSize: "var(--t-2xl)" }}>{title}</h1>
            {subtitle && <p className="text-ink-2">{subtitle}</p>}
          </div>
          {actions}
        </div>
        {children}
      </main>
    </div>
  );
}

export function Loading({ what = "dashboard" }: { what?: string }) {
  return <div className="panel text-ink-2" role="status">Loading {what}...</div>;
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="alert alert-bad" role="alert">{message}</div>;
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="panel stat">
      <span className="eyebrow">{label}</span>
      <span className="stat-value">{value}</span>
      {note && <span className="text-sm text-ink-3">{note}</span>}
    </div>
  );
}
