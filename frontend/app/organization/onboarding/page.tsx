"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import AppShell, { ErrorNote, Loading } from "@/components/AppShell";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";

const DAYS: { key: string; label: string }[] = [
  { key: "mon", label: "Mon" }, { key: "tue", label: "Tue" }, { key: "wed", label: "Wed" }, { key: "thu", label: "Thu" },
  { key: "fri", label: "Fri" }, { key: "sat", label: "Sat" }, { key: "sun", label: "Sun" },
];

interface Profile {
  organization: { name: string };
  completeness: { complete: boolean; missing: string[] };
  q1: { schedule: Record<string, string[][]> | null };
  q2: { typical_nightly_need: number | null };
}

type Day = { mode: "hours" | "all_day" | "closed"; start: string; end: string };
const defaultWeek = (): Record<string, Day> =>
  Object.fromEntries(DAYS.map((d) => [d.key, { mode: "hours", start: "09:00", end: "17:00" }]));

function weekFrom(schedule: Record<string, string[][]> | null): Record<string, Day> {
  if (!schedule) return defaultWeek();
  return Object.fromEntries(DAYS.map((d) => {
    const w = schedule[d.key]?.[0];
    if (!w) return [d.key, { mode: "closed", start: "09:00", end: "17:00" }];
    if (w[0] === "00:00" && w[1] === "24:00") return [d.key, { mode: "all_day", start: "09:00", end: "17:00" }];
    return [d.key, { mode: "hours", start: w[0], end: w[1] === "24:00" ? "23:59" : w[1] }]; // time inputs stop at 23:59
  }));
}

// Two things make an organization ready for deliveries: when it is open, and how much food it wants.
export default function OrgOnboardingPage() {
  const user = useRequireRole(["org_staff", "org_manager"]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [week, setWeek] = useState(defaultWeek);
  const [amount, setAmount] = useState("100");
  const [per, setPer] = useState<"day" | "week">("day");

  useEffect(() => {
    if (!user) return;
    api<Profile>("/orgs/me/profile").then((p) => {
      setProfile(p);
      setWeek(weekFrom(p.q1.schedule));
      if (p.q2.typical_nightly_need) setAmount(String(p.q2.typical_nightly_need));
    }).catch((e) => setError((e as Error).message));
  }, [user]);

  if (!user) return null;

  const setDay = (key: string, change: Partial<Day>) => setWeek({ ...week, [key]: { ...week[key], ...change } });
  const perDay = Math.max(1, Math.ceil(Number(amount || 0) / (per === "week" ? 7 : 1)));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const schedule = Object.fromEntries(DAYS.map((d) => {
        const day = week[d.key];
        return [d.key, day.mode === "closed" ? [] : day.mode === "all_day" ? [["00:00", "24:00"]] : [[day.start, day.end === "23:59" ? "24:00" : day.end]]];
      }));
      await api("/orgs/me/intake/Q1", { method: "PUT", body: { schedule } });
      const p = await api<Profile>("/orgs/me/intake/Q2", { method: "PUT", body: { typical_nightly_need: perDay } });
      setProfile(p);
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell icon="schedule" title="Get ready for deliveries" subtitle="Tell us when you're open and how much food you want.">
      <ErrorNote message={error} />
      {!profile ? <Loading /> : (
        <>
          <div className={`alert ${profile.completeness.complete ? "alert-good" : "alert-info"}`} role="status">
            {profile.completeness.complete
              ? <>You&apos;re ready: food can be routed to you. <Link className="font-semibold underline" href="/organization/dashboard">Go to your dashboard</Link></>
              : "Save your hours and how much food you want, and drivers can start bringing food."}
          </div>
          {saved && <div className="alert alert-good" role="status">Saved.</div>}

          <form className="panel flex flex-col gap-5" onSubmit={save}>
            <section className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2>When are you open?</h2>
                <button type="button" className="btn btn-ghost"
                  onClick={() => setWeek(Object.fromEntries(DAYS.map((d) => [d.key, { ...week[d.key], mode: "all_day" }])))}>
                  Open 24/7
                </button>
              </div>
              <div className="grid gap-2">
                {DAYS.map((d) => {
                  const day = week[d.key];
                  return (
                    <div key={d.key} className="grid grid-cols-[48px_auto_1fr] items-center gap-3">
                      <span className="text-sm font-semibold">{d.label}</span>
                      <select className="input" value={day.mode} onChange={(e) => setDay(d.key, { mode: e.target.value as Day["mode"] })}
                        aria-label={`${d.label} hours`}>
                        <option value="hours">Open</option>
                        <option value="all_day">All day</option>
                        <option value="closed">Closed</option>
                      </select>
                      {day.mode === "hours" ? (
                        <div className="flex items-center gap-2">
                          <input className="input" type="time" required value={day.start} aria-label={`${d.label} opens`}
                            onChange={(e) => setDay(d.key, { start: e.target.value })} />
                          <span className="text-ink-3">to</span>
                          <input className="input" type="time" required value={day.end} aria-label={`${d.label} closes`}
                            onChange={(e) => setDay(d.key, { end: e.target.value })} />
                        </div>
                      ) : <span className="text-sm text-ink-3">{day.mode === "all_day" ? "Open 24 hours" : "No deliveries"}</span>}
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="flex flex-col gap-3">
              <h2>How much food do you want?</h2>
              <div className="flex flex-wrap items-end gap-3">
                <label className="field"><span>Meals</span>
                  <input className="input num" type="number" min={1} required value={amount} onChange={(e) => setAmount(e.target.value)} />
                </label>
                <label className="field"><span>Per</span>
                  <select className="input" value={per} onChange={(e) => setPer(e.target.value as "day" | "week")}>
                    <option value="day">day</option>
                    <option value="week">week</option>
                  </select>
                </label>
              </div>
              {per === "week" && <p className="text-sm text-ink-2">That is about {perDay} meals a day.</p>}
            </section>

            <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? "Saving..." : "Save"}</button>
          </form>
        </>
      )}
    </AppShell>
  );
}
