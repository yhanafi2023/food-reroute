"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Brand } from "@/components/AppShell";
import { HOME_FOR_ROLE, useAuth } from "@/lib/auth";

const TYPES = [
  { value: "RESTAURANT", label: "Restaurant", text: "I have surplus food" },
  { value: "DRIVER", label: "Driver", text: "I can pick up and deliver" },
  { value: "ORGANIZATION", label: "Organization", text: "We receive and distribute food" },
];

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "RESTAURANT", address: "" });
  const [loc, setLoc] = useState<{ lat: number; lng: number } | null>(null);
  const [locNote, setLocNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  function shareLocation() {
    if (!navigator.geolocation) {
      setLocNote("Your browser cannot share location. We will use FIU as a starting point.");
      return;
    }
    setLocNote("Finding you...");
    navigator.geolocation.getCurrentPosition(
      (p) => { setLoc({ lat: p.coords.latitude, lng: p.coords.longitude }); setLocNote("Location saved."); },
      () => setLocNote("Location was not shared. We will use FIU as a starting point."),
      { timeout: 8000 },
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await signup({ ...form, ...(loc ?? {}) });
      router.push(HOME_FOR_ROLE[u.role]);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-6">
      <Brand />
      <h1 style={{ fontSize: "var(--t-3xl)" }}>Create an account</h1>
      <form className="panel flex flex-col gap-4" onSubmit={submit}>
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-sm font-semibold text-ink-2">Account type</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {TYPES.map((t) => (
              <label key={t.value} className={`flex cursor-pointer flex-col gap-1 rounded-lg border p-3 ${form.role === t.value ? "border-accent bg-wash" : "border-line"}`}>
                <span className="flex items-center gap-2 font-semibold">
                  <input type="radio" name="role" value={t.value} checked={form.role === t.value} onChange={() => setForm({ ...form, role: t.value })} />
                  {t.label}
                </span>
                <span className="text-sm text-ink-3">{t.text}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="field"><span>Name</span><input className="input" required value={form.name} onChange={set("name")} autoComplete="name" /></label>
        <label className="field"><span>Email</span><input className="input" type="email" required value={form.email} onChange={set("email")} autoComplete="email" /></label>
        <label className="field"><span>Password (at least 8 characters)</span><input className="input" type="password" minLength={8} required value={form.password} onChange={set("password")} autoComplete="new-password" /></label>
        <label className="field"><span>Address (optional)</span><input className="input" value={form.address} onChange={set("address")} autoComplete="street-address" /></label>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn btn-ghost" onClick={shareLocation}>Use my location</button>
          {locNote && <span className="text-sm text-ink-2" role="status">{locNote}</span>}
        </div>
        {error && <div className="alert alert-bad" role="alert">{error}</div>}
        <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? "Creating account..." : "Create account"}</button>
        <p className="text-sm text-ink-2">Already have an account? <Link className="font-semibold text-accent underline" href="/login">Log in</Link></p>
      </form>
    </div>
  );
}
