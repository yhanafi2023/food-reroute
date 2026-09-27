"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import AddressPicker, { type PickedAddress } from "@/components/AddressPicker";
import { TopNav } from "@/components/AppShell";
import Icon, { IconTile, type IconName } from "@/components/Icon";
import { HOME_FOR_ROLE, PASSWORD_MIN_LENGTH, useAuth } from "@/lib/auth";

type AccountType = "restaurant" | "receiver" | "volunteer";

const TYPES: { value: AccountType; label: string; text: string; icon: IconName }[] = [
  { value: "restaurant", label: "Restaurant", text: "I have surplus food", icon: "restaurant" },
  { value: "receiver", label: "Organization", text: "We receive and distribute food", icon: "community-org" },
  { value: "volunteer", label: "Driver", text: "I can pick up and deliver", icon: "driver" },
];

// Miami-Dade / FIU area, used only if the browser does not share a location.
const DEFAULT_LOCATION = { lat: 25.7580, lng: -80.3733 };

export default function SignupPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [type, setType] = useState<AccountType>("restaurant");
  const [form, setForm] = useState({ name: "", email: "", password: "", confirm: "", phone: "", orgName: "" });
  const [place, setPlace] = useState<PickedAddress | null>(null);
  const [loc, setLoc] = useState<{ lat: number; lng: number } | null>(null);
  const [locNote, setLocNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    // There is no password reset (no email), so catch a typo before the account exists.
    if (form.password !== form.confirm) {
      setError("The passwords do not match.");
      return;
    }
    // Every pickup and drop-off is routed to this point, so it must come from the address, not a guess.
    if (type !== "volunteer" && !place) {
      setError("Find your address and pick it from the list, so drivers are routed to the right place.");
      return;
    }
    setBusy(true);
    setError(null);
    const { lat, lng } = loc ?? DEFAULT_LOCATION;
    try {
      const u = type === "volunteer"
        ? await register("/auth/register-volunteer", {
            name: form.name, email: form.email, password: form.password, phone: form.phone, home_lat: lat, home_lng: lng,
          })
        : await register("/auth/register-organization", {
            kind: type, organization_name: form.orgName, address: place!.address, lat: place!.lat, lng: place!.lng,
            manager_name: form.name, manager_email: form.email, manager_password: form.password, manager_phone: form.phone,
          });
      router.push(HOME_FOR_ROLE[u.role]);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
    <TopNav />
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-6">
      <h1 style={{ fontSize: "var(--t-3xl)" }}>Create an account</h1>
      <form className="panel flex flex-col gap-4" onSubmit={submit}>
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-sm font-semibold text-ink-2">Account type</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {TYPES.map((t) => (
              <label key={t.value} className={`flex cursor-pointer flex-col gap-1 rounded-lg border p-3 ${type === t.value ? "border-accent bg-wash" : "border-line"}`}>
                <IconTile name={t.icon} size={48} tone={type === t.value ? "accent" : "light"} className="mb-1" />
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
        <label className="field"><span>Password (at least {PASSWORD_MIN_LENGTH} characters)</span>
          <input className="input" type="password" required minLength={PASSWORD_MIN_LENGTH} value={form.password} onChange={set("password")} autoComplete="new-password" />
        </label>
        <label className="field"><span>Confirm password</span>
          <input className="input" type="password" required minLength={PASSWORD_MIN_LENGTH} value={form.confirm} onChange={set("confirm")} autoComplete="new-password" />
        </label>
        <label className="field"><span>Phone (optional)</span><input className="input" value={form.phone} onChange={set("phone")} autoComplete="tel" /></label>
        {type !== "volunteer" ? (
          <AddressPicker label={type === "restaurant" ? "Restaurant address (where food is picked up)" : "Address (where food is dropped off)"}
            value={place} onChange={setPlace} />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn btn-ghost pl-3" onClick={shareLocation}><Icon name="locate" size={24} />Use my location</button>
            {locNote && <span className="text-sm text-ink-2" role="status">{locNote}</span>}
          </div>
        )}
        {error && <div className="alert alert-bad" role="alert">{error}</div>}
        <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? "Creating account..." : "Create account"}</button>
        <p className="text-sm text-ink-2">Already have an account? <Link className="font-semibold text-accent underline" href="/login">Log in</Link></p>
      </form>
    </div>
    </>
  );
}
