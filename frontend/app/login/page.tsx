"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { TopNav } from "@/components/AppShell";
import { DEMO_CODE, HOME_FOR_ROLE, useAuth } from "@/lib/auth";

const DEMO = [
  { role: "Restaurant", email: "manager@casa-demo.example.com", who: "Casa Demo Cocina" },
  { role: "Volunteer", email: "marcus@volunteer-demo.example.com", who: "Marcus" },
  { role: "Organization", email: "manager@shelter-demo.example.com", who: "Demo Night Shelter" },
  { role: "Admin", email: "admin@foodflow-demo.example.com", who: "Network view" },
];

export default function LoginPage() {
  const { requestCode, verifyCode, user, ready } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace(HOME_FOR_ROLE[user.role]);
  }, [ready, user, router]);

  async function sendCode(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await requestCode(email);
      setCodeSent(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function go(e: string, c: string) {
    setBusy(true);
    setError(null);
    try {
      const u = await verifyCode(e, c);
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
          {!codeSent ? (
            <form className="panel flex flex-col gap-4" onSubmit={sendCode}>
              <label className="field"><span>Email</span>
                <input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </label>
              {error && <div className="alert alert-bad" role="alert">{error}</div>}
              <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? "Sending code..." : "Send sign-in code"}</button>
              <p className="text-sm text-ink-2">New here? <Link className="font-semibold text-accent underline" href="/signup">Create an account</Link></p>
            </form>
          ) : (
            <form className="panel flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); go(email, code); }}>
              <p className="text-ink-2">We sent a 6 digit code to <strong>{email}</strong>. Enter it below.</p>
              <label className="field"><span>Code</span>
                <input className="input mono" inputMode="numeric" pattern="\d{6}" maxLength={6} required autoFocus
                       value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
              </label>
              {error && <div className="alert alert-bad" role="alert">{error}</div>}
              <button className="btn btn-primary btn-lg" disabled={busy || code.length !== 6}>{busy ? "Checking..." : "Verify and log in"}</button>
              <button type="button" className="text-sm text-ink-3 underline" onClick={() => { setCodeSent(false); setCode(""); setError(null); }}>
                Use a different email
              </button>
            </form>
          )}
        </section>
        <section className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <span className="eyebrow">Demo login</span>
            <p className="text-ink-2">One click, no code needed.</p>
          </div>
          <div className="flex flex-col gap-3">
            {DEMO.map((d) => (
              <button key={d.email} className="btn btn-ghost btn-lg justify-between" disabled={busy}
                onClick={() => go(d.email, DEMO_CODE)} aria-label={`Demo login as ${d.role}`}>
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
