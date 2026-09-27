"use client";
import Link from "next/link";
import { useState } from "react";
import AppShell, { ErrorNote, LiveStatus, Loading, Stat } from "@/components/AppShell";
import Icon from "@/components/Icon";
import DeliveryMap from "@/components/DeliveryMap";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { clock, currentTrip, number } from "@/lib/format";
import type { OrgDeliveries, OrgDeliveryItem } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

function ReceiptForm({ item, busy, onSubmit }: {
  item: OrgDeliveryItem; busy: boolean;
  onSubmit: (condition: "accepted" | "partially_accepted" | "rejected", receivedMeals: number, note: string) => void;
}) {
  const [receivedMeals, setReceivedMeals] = useState(String(item.stop.allocated_meals));
  const [note, setNote] = useState("");
  const full = Number(receivedMeals) >= item.stop.allocated_meals;
  return (
    <div className="flex flex-col gap-3">
      <label className="field"><span>Meals actually received</span>
        <input className="input num" type="number" min={0} max={item.stop.allocated_meals} value={receivedMeals} onChange={(e) => setReceivedMeals(e.target.value)} />
      </label>
      <label className="field"><span>Notes (only needed if rejecting or short)</span><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <div className="grid grid-cols-2 gap-3">
        <button className="btn btn-good btn-lg" disabled={busy}
          onClick={() => onSubmit(full ? "accepted" : "partially_accepted", Number(receivedMeals), note)}>
          Confirm receipt
        </button>
        <button className="btn btn-danger btn-lg" disabled={busy} onClick={() => onSubmit("rejected", 0, note)}>Reject</button>
      </div>
    </div>
  );
}

export default function OrganizationDashboardPage() {
  const user = useRequireRole(["org_staff", "org_manager"]);
  const { data, error, refresh, updatedAt } = usePoll<OrgDeliveries>(user ? "/orgs/me/deliveries" : null);
  const [need, setNeed] = useState("25");
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

  const mealsReceived = data?.history.reduce((sum, i) => sum + (i.stop.received_meals ?? 0), 0) ?? 0;

  return (
    <AppShell icon="community-org" title={user.name} subtitle="See what's on the way. Confirm what arrives."
      actions={<div className="flex flex-wrap items-center gap-2"><LiveStatus updatedAt={updatedAt} error={error} /></div>}>
      <ErrorNote message={error} onRetry={refresh} stale={!!data} />
      {note && <div className={`alert ${note.kind === "good" ? "alert-good" : "alert-bad"}`} role="status">{note.text}</div>}
      {!data ? <Loading /> : (
        <>
          <section className="flex flex-col gap-3" aria-labelledby="incoming-title">
            <h2 id="incoming-title" style={{ fontSize: "var(--t-lg)" }}>Incoming deliveries</h2>
            {data.incoming.length === 0 && data.to_confirm.length === 0 && (
              <p className="panel text-ink-2">Nothing on the way right now. Matched deliveries appear here with a live map.</p>
            )}
            {[...data.to_confirm, ...data.incoming].map((item) => {
              const trip = item.rescue.trips.find((t) => t.stops.some((s) => s.id === item.stop.id)) ?? currentTrip(item.rescue.trips);
              return (
              <article key={item.stop.id} className="panel panel-accent flex flex-col gap-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex flex-col gap-1">
                    <strong className="flex items-center gap-2 text-xl" style={{ fontFamily: "var(--ff-display)" }}><Icon name="van" size={30} />{item.stop.allocated_meals} meals incoming</strong>
                    <span className="text-ink-2">
                      {trip?.carrier.type === "volunteer" ? trip.carrier.first_name : trip?.carrier.label} · from {item.rescue.restaurant.name}
                    </span>
                    <span className="text-sm text-ink-3">{item.rescue.category.replace("_", "-")} food · pickup by {clock(item.rescue.pickup_deadline)}</span>
                  </div>
                  <span className={`chip ${item.stop.status === "delivered" ? "chip-good" : ""}`}>{item.stop.status === "delivered" ? "Delivered, please confirm" : "on the way"}</span>
                </div>
                {trip && <DeliveryMap rescue={item.rescue} trip={trip} height={280} />}
                {item.stop.status === "delivered" ? (
                  <ReceiptForm item={item} busy={busy}
                    onSubmit={(condition, receivedMeals, noteText) => act(() => api(`/stops/${item.stop.id}/receipt`, {
                      method: "POST", body: { condition, received_meals: receivedMeals, reject_note: noteText, reject_reason: condition === "rejected" ? "other" : undefined },
                    }), condition === "rejected" ? "Marked as rejected." : `Confirmed ${receivedMeals} meals. Thank you!`)}
                  />
                ) : (
                  <>
                    {item.stop.dropoff_code && (
                      <div className="alert alert-info flex flex-wrap items-center justify-between gap-3">
                        <span>Give this code to the driver when they hand over the food.</span>
                        <span className="mono font-semibold" style={{ fontSize: "var(--t-2xl)", letterSpacing: "0.2em" }}>{item.stop.dropoff_code}</span>
                      </div>
                    )}
                    <p className="text-sm text-ink-3">You can confirm receipt once the carrier marks it delivered.</p>
                  </>
                )}
              </article>
              );
            })}
          </section>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
            <form className="panel flex flex-col gap-4 self-start" aria-labelledby="need-title"
              onSubmit={(e) => {
                e.preventDefault();
                act(() => api("/orgs/me/need", { method: "POST", body: { meals: Number(need) } }),
                  "Need updated. FoodFlow will route matching food to you tonight.");
              }}>
              <h2 id="need-title" style={{ fontSize: "var(--t-lg)" }}>Tonight&apos;s need</h2>
              <label className="field"><span>Meals needed tonight</span><input className="input num" type="number" min={0} required value={need} onChange={(e) => setNeed(e.target.value)} /></label>
              <button className="btn btn-primary btn-lg" disabled={busy}>Update need</button>
              <p className="text-sm text-ink-3">
                Onboarding (hours, food categories, records) is answered once at signup.
                See <Link className="font-semibold text-accent underline" href="/organization/onboarding">onboarding status</Link>.
              </p>
            </form>

            <div className="flex flex-col gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Stat label="Meals received" icon="hot-meal" value={number(mealsReceived)} note={`${data.history.length} deliveries`} />
                <section className="panel flex flex-col gap-2">
                  <span className="eyebrow">Recently received</span>
                  {data.history.length === 0 ? <span className="text-ink-3">None yet.</span> : data.history.slice(0, 5).map((r) => (
                    <span key={r.stop.id} className="text-sm">
                      {r.stop.received_meals ?? r.stop.allocated_meals} meals from {r.rescue.restaurant.name}{r.rescue.is_fictional ? " (demo)" : ""}
                    </span>
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
