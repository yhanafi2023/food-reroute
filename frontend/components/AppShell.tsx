"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { HOME_FOR_ROLE, useAuth } from "@/lib/auth";
import Icon, { IconTile, type IconName } from "./Icon";
import type { Role } from "@/lib/types";

// Pickup (amber) to drop off (mint) along one route.
export function BrandMark({ size = 28, light = true }: { size?: number; light?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden>
      <circle cx="6" cy="21" r="4" fill="#f59e0b" />
      <circle cx="22" cy="7" r="4" fill="#34d399" />
      <path d="M6 21 C 6 12, 22 16, 22 7" stroke={light ? "#22d3ee" : "#3b82f6"} strokeWidth="3" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function Brand({ light = false }: { light?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2 no-underline" aria-label="FoodFlow home">
      <BrandMark light={light} />
      <span className="text-xl font-bold tracking-tight text-ink" style={{ fontFamily: "var(--ff-display)" }}>
        FoodFlow
      </span>
    </Link>
  );
}

const ROLE_LINKS: Record<Role, { href: string; label: string }[]> = {
  restaurant_staff: [
    { href: "/restaurant/dashboard", label: "Dashboard" },
    { href: "/restaurant/surplus-log", label: "Surplus log" },
  ],
  restaurant_manager: [
    { href: "/restaurant/dashboard", label: "Dashboard" },
    { href: "/restaurant/surplus-log", label: "Surplus log" },
  ],
  volunteer: [{ href: "/driver/dashboard", label: "Dashboard" }],
  org_staff: [
    { href: "/organization/dashboard", label: "Dashboard" },
    { href: "/organization/onboarding", label: "Onboarding" },
  ],
  org_manager: [
    { href: "/organization/dashboard", label: "Dashboard" },
    { href: "/organization/onboarding", label: "Onboarding" },
  ],
  admin: [
    { href: "/admin/dashboard", label: "Network" },
    { href: "/admin/prospects", label: "Prospects" },
  ],
};
export const ROLE_ICON: Record<Role, IconName> = {
  restaurant_staff: "restaurant",
  restaurant_manager: "restaurant",
  volunteer: "driver",
  org_staff: "community-org",
  org_manager: "community-org",
  admin: "stats",
};
const PUBLIC_LINKS = [
  { href: "/#how", label: "How it works" },
  { href: "/impact", label: "Impact" },
];

// Top navigation: dark bar, brand left, links, account actions right.
// Below 768px it collapses into a full-screen menu that closes on Escape and on link click.
export function TopNav() {
  const { user, ready, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const links = [...(user ? ROLE_LINKS[user.role] : []), ...PUBLIC_LINKS];

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    menuRef.current?.querySelector<HTMLElement>("a,button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  const signOut = () => {
    setOpen(false);
    logout();
    router.push("/login");
  };
  const active = (href: string) => (href === pathname ? "page" : undefined);

  return (
    <header className="sticky top-0 z-[1100] border-b border-line bg-panel/95 text-ink backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4">
        <div className="flex items-center gap-8">
          <Brand light />
          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {links.map((l) => (
              <Link key={l.href} href={l.href} aria-current={active(l.href)}
                className={`rounded-full px-4 py-2 text-sm font-semibold no-underline hover:bg-white/10 ${active(l.href) ? "bg-white/15 text-white" : "text-white/85"}`}>
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="hidden items-center gap-2 md:flex">
          {!ready ? null : user ? (
            <>
              <Link href={HOME_FOR_ROLE[user.role]} className="flex items-center gap-2 rounded-full py-1.5 pl-1.5 pr-4 text-sm font-semibold text-ink/85 no-underline hover:bg-white/10">
                <Icon name={ROLE_ICON[user.role]} size={28} className="rounded-full bg-[#eef2f7]" />
                {user.name}
              </Link>
              <button onClick={signOut} className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-ink">Log out</button>
            </>
          ) : (
            <>
              <Link href="/login" className="rounded-full px-4 py-2 text-sm font-semibold text-ink no-underline hover:bg-white/10">Log in</Link>
              <Link href="/signup" className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white no-underline hover:bg-accent-ink">Sign up</Link>
            </>
          )}
        </div>
        <button className="grid h-11 w-11 place-items-center rounded-full hover:bg-white/10 md:hidden" aria-label="Open menu"
          aria-expanded={open} aria-controls="mobile-menu" onClick={() => setOpen(true)}>
          <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden><path d="M3 6h16M3 11h16M3 16h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
        </button>
      </div>

      {open && (
        <div id="mobile-menu" ref={menuRef} role="dialog" aria-modal="true" aria-label="Menu"
          className="fixed inset-0 z-[1200] flex flex-col bg-paper px-4 pb-8 text-ink md:hidden">
          <div className="flex h-16 items-center justify-between">
            <Brand light />
            <button className="grid h-11 w-11 place-items-center rounded-full hover:bg-white/10" aria-label="Close menu" onClick={() => setOpen(false)}>
              <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden><path d="M5 5l12 12M17 5L5 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
            </button>
          </div>
          <nav className="flex flex-1 flex-col gap-1 pt-4" aria-label="Mobile">
            {links.map((l) => (
              <Link key={l.href} href={l.href} onClick={() => setOpen(false)} aria-current={active(l.href)}
                className="rounded-lg px-2 py-3 text-2xl font-bold text-ink no-underline hover:bg-white/10" style={{ fontFamily: "var(--ff-display)" }}>
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="flex flex-col gap-3">
            {user ? (
              <>
                <span className="flex items-center gap-2 text-sm text-ink-3">
                  <Icon name={ROLE_ICON[user.role]} size={28} className="rounded-full bg-[#eef2f7]" />
                  Signed in as {user.name} ({user.role.toLowerCase()})
                </span>
                <button onClick={signOut} className="min-h-12 rounded-full bg-accent text-lg font-semibold text-white">Log out</button>
              </>
            ) : (
              <>
                <Link href="/signup" onClick={() => setOpen(false)} className="grid min-h-12 place-items-center rounded-full bg-accent text-lg font-semibold text-white no-underline">Sign up</Link>
                <Link href="/login" onClick={() => setOpen(false)} className="grid min-h-12 place-items-center rounded-full border border-line text-lg font-semibold text-ink no-underline">Log in</Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}

export default function AppShell({ title, subtitle, children, actions, icon }: {
  title: string; subtitle?: string; children: ReactNode; actions?: ReactNode; icon?: IconName;
}) {
  return (
    <div className="min-h-screen">
      <TopNav />
      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex items-center gap-4">
            {icon && <IconTile name={icon} size={56} />}
            <div className="flex flex-col gap-1">
              <h1 style={{ fontSize: "var(--t-2xl)" }}>{title}</h1>
              {subtitle && <p className="text-ink-2">{subtitle}</p>}
            </div>
          </div>
          {actions}
        </div>
        {children}
      </main>
    </div>
  );
}

// Placeholder blocks shaped like the content that is loading.
export function Loading({ what = "dashboard", rows = 3 }: { what?: string; rows?: number }) {
  return (
    <div className="flex flex-col gap-4" role="status" aria-live="polite">
      <span className="sr-only">Loading {what}...</span>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-hidden>
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-24" />)}
      </div>
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton h-32" aria-hidden />)}
    </div>
  );
}

export function ErrorNote({ message, onRetry, stale }: { message: string | null; onRetry?: () => void; stale?: boolean }) {
  if (!message) return null;
  return (
    <div className="alert alert-bad flex flex-wrap items-center justify-between gap-3" role="alert">
      <span>{message}{stale ? " Showing the last data we received." : ""}</span>
      {onRetry && <button className="btn btn-ghost" onClick={onRetry}>Try again</button>}
    </div>
  );
}

// "Live · updated 2 s ago" or "Reconnecting..." next to a polled view.
export function LiveStatus({ updatedAt, error }: { updatedAt: number | null; error: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  if (error) return <span className="chip chip-bad" role="status">Reconnecting...</span>;
  if (!updatedAt) return <span className="chip" role="status">Connecting...</span>;
  const secs = Math.max(0, Math.round((now - updatedAt) / 1000));
  return (
    <span className="chip chip-good" role="status" aria-live="off">
      <i aria-hidden className="inline-block h-2 w-2 rounded-full bg-good" /> Live · updated {secs < 2 ? "just now" : `${secs}s ago`}
    </span>
  );
}

export function Stat({ label, value, note, icon }: { label: string; value: ReactNode; note?: string; icon?: IconName }) {
  return (
    <div className="panel stat">
      <span className="flex items-start justify-between gap-2">
        <span className="eyebrow">{label}</span>
        {icon && <Icon name={icon} size={28} />}
      </span>
      <span className="stat-value">{value}</span>
      {note && <span className="text-sm text-ink-3">{note}</span>}
    </div>
  );
}

export function Section({ title, children, aside, id }: { title: string; children: ReactNode; aside?: ReactNode; id?: string }) {
  return (
    <section className="flex flex-col gap-3" aria-labelledby={id}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={id} style={{ fontSize: "var(--t-lg)" }}>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
