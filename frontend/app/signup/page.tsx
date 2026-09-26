"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Shell } from "@/components/Shell";
import { api } from "@/lib/api";
import { HOME, useAuth, WORKSPACE_FOR_ROLE } from "@/lib/auth";

type AccountType = "restaurant" | "receiver" | "volunteer";

const TYPES: { value: AccountType; label: string; text: string }[] = [
  { value: "restaurant", label: "Restaurant", text: "I have surplus food" },
  { value: "receiver", label: "Organization", text: "We receive and distribute food" },
  { value: "volunteer", label: "Volunteer", text: "I can pick up and deliver" },
];

// Miami-Dade / FIU area, used only if the browser does not share a location.
const DEFAULT_LOCATION = { lat: 25.7580, lng: -80.3733 };

export default function SignupPage() {
  const { verifyCode } = useAuth();
  const router = useRouter();
  const [type, setType] = useState<AccountType>("restaurant");
  const [form, setForm] = useState({ name: "", email: "", phone: "", orgName: "", address: "" });
  const [loc, setLoc] = useState<{ lat: number; lng: number } | null>(null);
  const [locNote, setLocNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);
  const [code, setCode] = useState("");

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  function shareLocation() {
    if (!navigator.geolocation) {
      setLocNote("Your browser cannot share location. We will use a location near FIU as a starting point.");
      return;
    }
    setLocNote("Finding you...");
    navigator.geolocation.getCurrentPosition(
      (p) => { setLoc({ lat: p.coords.latitude, lng: p.coords.longitude }); setLocNote("Location saved."); },
      () => setLocNote("Location was not shared. We will use a location near FIU as a starting point."),
      { timeout: 8000 },
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { lat, lng } = loc ?? DEFAULT_LOCATION;
    try {
      if (type === "volunteer") {
        await api("/auth/register-volunteer", {
          method: "POST", body: { name: form.name, email: form.email, phone: form.phone, home_lat: lat, home_lng: lng },
        });
      } else {
        await api("/auth/register-organization", {
          method: "POST",
          body: {
            kind: type, organization_name: form.orgName, address: form.address, lat, lng,
            manager_name: form.name, manager_email: form.email, manager_phone: form.phone,
          },
        });
      }
      setRegisteredEmail(form.email);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await verifyCode(registeredEmail!, code);
      router.push(HOME[WORKSPACE_FOR_ROLE[u.role]]);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  if (registeredEmail) {
    return (
      <Shell>
      <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-6">
        <h1 style={{ fontSize: "var(--t-3xl)" }}>Check your email</h1>
        <form className="panel flex flex-col gap-4" onSubmit={verify}>
          <p className="text-ink-2">We sent a 6 digit sign-in code to <strong>{registeredEmail}</strong>.</p>
          <label className="field"><span>Code</span>
            <input className="input mono" inputMode="numeric" pattern="\d{6}" maxLength={6} required autoFocus
                   value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
          </label>
          {error && <div className="alert alert-bad" role="alert">{error}</div>}
          <button className="btn btn-primary btn-lg" disabled={busy || code.length !== 6}>{busy ? "Checking..." : "Verify and continue"}</button>
        </form>
      </div>
      </Shell>
    );
  }

  return (
    <Shell>
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-6">
      <h1 style={{ fontSize: "var(--t-3xl)" }}>Create an account</h1>
      <form className="panel flex flex-col gap-4" onSubmit={submit}>
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-sm font-semibold text-ink-2">Account type</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {TYPES.map((t) => (
              <label key={t.value} className={`flex cursor-pointer flex-col gap-1 rounded-lg border p-3 ${type === t.value ? "border-accent bg-wash" : "border-line"}`}>
                <span className="flex items-center gap-2 font-semibold">
                  <input type="radio" name="type" value={t.value} checked={type === t.value} onChange={() => setType(t.value)} />
                  {t.label}
                </span>
                <span className="text-sm text-ink-3">{t.text}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {type !== "volunteer" && (
          <label className="field"><span>{type === "restaurant" ? "Restaurant" : "Organization"} name</span>
            <input className="input" required value={form.orgName} onChange={set("orgName")} />
          </label>
        )}
        <label className="field"><span>Your name</span><input className="input" required value={form.name} onChange={set("name")} autoComplete="name" /></label>
        <label className="field"><span>Email</span><input className="input" type="email" required value={form.email} onChange={set("email")} autoComplete="email" /></label>
        <label className="field"><span>Phone (optional)</span><input className="input" value={form.phone} onChange={set("phone")} autoComplete="tel" /></label>
        {type !== "volunteer" && (
          <label className="field"><span>Address (optional)</span><input className="input" value={form.address} onChange={set("address")} autoComplete="street-address" /></label>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn btn-ghost" onClick={shareLocation}>Use my location</button>
          {locNote && <span className="text-sm text-ink-2" role="status">{locNote}</span>}
        </div>
        {error && <div className="alert alert-bad" role="alert">{error}</div>}
        <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? "Creating account..." : "Create account"}</button>
        <p className="text-sm text-ink-2">Already have an account? <Link className="font-semibold text-accent underline" href="/login">Log in</Link></p>
      </form>
    </div>
    </Shell>
  );
}
