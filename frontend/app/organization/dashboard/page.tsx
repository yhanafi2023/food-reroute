"use client";
import { useState } from "react";
import AppShell, { ErrorNote, LiveStatus, Loading, Stat } from "@/components/AppShell";
import DeliveryMap from "@/components/DeliveryMap";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { clock, number, until } from "@/lib/format";
import type { OrganizationDashboard } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

function localInput(hoursAhead: number) {
  const d = new Date(Date.now() + hoursAhead * 3600000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const STATUS_TEXT: Record<string, string> = {
  HEADING_TO_RESTAURANT: "Driver heading to the restaurant",
  ARRIVED_AT_RESTAURANT: "Driver at the restaurant",
  PICKED_UP: "Food picked up",
  DELIVERING: "On the way to you",
  DELIVERED: "Delivered. Please confirm receipt",
};

export default function OrganizationDashboardPage() {
  const user = useRequireRole("ORGANIZATION");
  const { data, error, refresh, updatedAt } = usePoll<OrganizationDashboard>(user ? "/organizations/dashboard" : null);
  const [form, setForm] = useState({ meals_needed: "25", preferred_food: "Any", deadline: localInput(6), priority: "MEDIUM" });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ kind: "good" | "bad"; text: string } | null>(null);

  if (!user) return null;

  async function act(fn: () => Promise<unknown>, success: string) {
    setBusy(true);
    setNote(null);
    try {
      await fn();
      setNote({ kind: "good", text: success });
      await refresh();
    } catch (e) {
      setNote({ kind: "bad", text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <AppShell title={data?.organization.name ?? "Organization"} subtitle="Post what you need. Confirm what arrives."
      actions={<div className="flex flex-wrap items-center gap-2"><span className="chip">Fictional demo organization</span><LiveStatus updatedAt={updatedAt} error={error} /></div>}>
      <ErrorNote message={error} onRetry={refresh} stale={!!data} />
      {note && <div className={`alert ${note.kind === "good" ? "alert-good" : "alert-bad"}`} role="status">{note.text}</div>}
      {!data ? <Loading /> : (
        <>
          <section className="flex flex-col gap-3" aria-labelledby="incoming-title">
            <h2 id="incoming-title" style={{ fontSize: "var(--t-lg)" }}>Incoming deliveries</h2>
            {data.incoming.length === 0 && <p className="panel text-ink-2">Nothing on the way right now. Matched deliveries appear here with a live map.</p>}
            {data.incoming.map((item) => {
              const d = item.delivery;
              return (
                <article key={d.id} className="panel panel-accent flex flex-col gap-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex flex-col gap-1">
                      <strong className="text-xl" style={{ fontFamily: "var(--ff-display)" }}>{item.my_meals} meals incoming</strong>
                      <span className="text-ink-2">Driver: {d.driver_name} · from {d.restaurant.name}</span>
                      <span className="text-sm text-ink-3">{d.food_type} · you are stop {item.my_stop_number} of {d.stops.length}</span>
                    </div>
                    <span className={`chip ${d.status === "DELIVERED" ? "chip-good" : ""}`}>{STATUS_TEXT[d.status] ?? d.status}</span>
                  </div>
                  <DeliveryMap delivery={d} height={300} />
                  <button className="btn btn-good btn-lg" disabled={busy || !item.can_confirm}
                    onClick={() => act(() => api(`/deliveries/${d.id}/confirm`, { method: "POST" }), `Confirmed ${item.my_meals} meals. Thank you!`)}>
                    {item.can_confirm ? `Confirm Receipt of ${item.my_meals} meals` : "Confirm Receipt (after the driver marks it delivered)"}
                  </button>
                </article>
              );
            })}
          </section>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
            <form className="panel flex flex-col gap-4 self-start" aria-labelledby="need-title"
              onSubmit={(e) => {
                e.preventDefault();
                act(() => api("/organizations/needs", { method: "POST", body: {
                  meals_needed: Number(form.meals_needed), preferred_food: form.preferred_food,
                  deadline: new Date(form.deadline).toISOString(), priority: form.priority,
                } }), "Need posted. FoodFlow will route matching food to you.");
              }}>
              <h2 id="need-title" style={{ fontSize: "var(--t-lg)" }}>Post a need</h2>
              <div className="grid grid-cols-2 gap-4">
                <label className="field"><span>Meals needed</span><input className="input num" type="number" min={1} required value={form.meals_needed} onChange={set("meals_needed")} /></label>
                <label className="field"><span>Priority</span>
                  <select className="input" value={form.priority} onChange={set("priority")}>
                    <option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option>
                  </select>
                </label>
              </div>
              <label className="field"><span>Preferred food</span><input className="input" value={form.preferred_food} onChange={set("preferred_food")} /></label>
              <label className="field"><span>Needed by</span><input className="input" type="datetime-local" required value={form.deadline} onChange={set("deadline")} /></label>
              <button className="btn btn-primary btn-lg" disabled={busy}>Post need</button>
            </form>

            <div className="flex flex-col gap-4">
              <section className="panel flex flex-col gap-4" aria-labelledby="needs-title">
                <h3 id="needs-title">Your needs</h3>
                {data.needs.length === 0 && <p className="text-ink-3">No needs posted.</p>}
                {data.needs.map((n) => {
                  const pct = Math.min(100, Math.round((n.meals_fulfilled / n.meals_needed) * 100));
                  return (
                    <div key={n.id} className="flex flex-col gap-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-semibold">{n.meals_fulfilled} of {n.meals_needed} meals</span>
                        <span className="flex gap-1">
                          <span className={`chip ${n.priority === "HIGH" ? "chip-warn" : ""}`}>{n.priority}</span>
                          <span className={`chip ${n.status === "FULFILLED" ? "chip-good" : ""}`}>{n.status === "FULFILLED" ? "fulfilled" : `by ${clock(n.deadline)}, ${until(n.deadline)}`}</span>
                        </span>
                      </div>
                      <div className={`bar ${n.status === "FULFILLED" ? "bar-good" : ""}`} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${pct}% fulfilled`}>
                        <i style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </section>
              <div className="grid gap-4 sm:grid-cols-2">
                <Stat label="Meals received" value={number(data.meals_received)} />
                <section className="panel flex flex-col gap-2">
                  <span className="eyebrow">Recently received</span>
                  {data.received.length === 0 ? <span className="text-ink-3">None yet.</span> : data.received.map((r) => (
                    <span key={r.delivery.id} className="text-sm">{r.my_meals} meals from {r.delivery.restaurant.name}{r.delivery.is_demo_seed ? " (demo)" : ""}</span>
                  ))}
                </section>
              </div>
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
