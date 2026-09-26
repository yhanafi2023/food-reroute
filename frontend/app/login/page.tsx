"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { TopNav } from "@/components/AppShell";
import { HOME_FOR_ROLE, useAuth } from "@/lib/auth";

const DEMO = [
  { role: "Restaurant", email: "restaurant@demo.com", who: "ABC Restaurant" },
  { role: "Driver", email: "driver@demo.com", who: "Marcus" },
  { role: "Organization", email: "org@demo.com", who: "Community Food Bank" },
  { role: "Admin", email: "admin@demo.com", who: "Network view" },
];

export default function LoginPage() {
  const { login, user, ready } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace(HOME_FOR_ROLE[user.role]);
  }, [ready, user, router]);

  async function go(e: string, p: string) {
    setBusy(true);
    setError(null);
    try {
      const u = await login(e, p);
      router.push(HOME_FOR_ROLE[u.role]);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
    <TopNav />
    <div className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-6">
      <div className="grid gap-8 md:grid-cols-2">
        <section className="flex flex-col gap-4">
          <h1 style={{ fontSize: "var(--t-3xl)" }}>Log in</h1>
          <form className="panel flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); go(email, password); }}>
            <label className="field"><span>Email</span>
              <input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="field"><span>Password</span>
              <input className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            {error && <div className="alert alert-bad" role="alert">{error}</div>}
            <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? "Logging in..." : "Log in"}</button>
            <p className="text-sm text-ink-2">New here? <Link className="font-semibold text-accent underline" href="/signup">Create an account</Link></p>
          </form>
        </section>
        <section className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <span className="eyebrow">Demo login</span>
            <p className="text-ink-2">One click, password demo1234.</p>
          </div>
          <div className="flex flex-col gap-3">
            {DEMO.map((d) => (
              <button key={d.email} className="btn btn-ghost btn-lg justify-between" disabled={busy}
                onClick={() => go(d.email, "demo1234")} aria-label={`Demo login as ${d.role}`}>
                <span>{d.role}</span>
                <span className="text-sm font-normal text-ink-3">{d.who}</span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
    </>
  );
}
