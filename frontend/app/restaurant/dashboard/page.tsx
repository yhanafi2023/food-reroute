"use client";
import { useEffect, useRef, useState } from "react";
import AppShell, { ErrorNote, LiveStatus, Loading, Stat } from "@/components/AppShell";
import DeliveryMap, { RescueAreaMap } from "@/components/DeliveryMap";
import MatchCard from "@/components/MatchCard";
import RescueSequence from "@/components/RescueSequence";
import StatusTimeline from "@/components/StatusTimeline";
import { api, isAbort } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { clock, currentTrip, defaultDeadline, number, until } from "@/lib/format";
import type { CreateRescueResponse, FoodUnit, MatchingExplanation, Rescue } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const UNITS: { value: FoodUnit; label: string }[] = [
  { value: "individual_meal", label: "Individual meals" }, { value: "bag", label: "Bags" }, { value: "box", label: "Boxes" },
  { value: "tray", label: "Trays" }, { value: "half_pan", label: "Half pans" }, { value: "full_pan", label: "Full pans" },
];

const EMPTY = { quantity: "6", unit: "tray" as FoodUnit, pickup_deadline: "", description: "", attested: false };

// The driver types this at pickup to prove they have the food; until it is shown here, nobody can.
function PickupCode({ rescue }: { rescue: Rescue }) {
  const waiting = ["posted", "matched", "en_route_pickup"].includes(rescue.status);
  if (!rescue.pickup_code || !waiting) return null;
  return (
    <div className="alert alert-info flex flex-wrap items-center justify-between gap-3">
      <span>Give this code to the driver when they pick up the food.</span>
      <span className="mono font-semibold" style={{ fontSize: "var(--t-2xl)", letterSpacing: "0.2em" }}>{rescue.pickup_code}</span>
    </div>
  );
}

export default function RestaurantDashboardPage() {
  const user = useRequireRole(["restaurant_staff", "restaurant_manager"]);
  const { data: rescues, error, refresh, updatedAt } = usePoll<Rescue[]>(user ? "/rescues" : null);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  const [form, setForm] = useState(() => ({ ...EMPTY, pickup_deadline: defaultDeadline() }));
  const [finding, setFinding] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateRescueResponse | null>(null);
  const [explanation, setExplanation] = useState<MatchingExplanation | null>(null);

  if (!user) return null;

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!form.attested) {
      setFormError("Please confirm the food was stored and handled safely.");
      return;
    }
    setFinding(true);
    setResult(null);
    setExplanation(null);
    const ctrl = new AbortController();
    pending.current = ctrl;
    // Gives the rescue-search animation (components/RescueSequence) room to play its full
    // dispatch -> searching -> optimizing -> match found sequence before the real card appears.
    const minWait = new Promise((r) => setTimeout(r, 2900));
    try {
      const [res] = await Promise.all([
        api<CreateRescueResponse>("/rescues", {
          method: "POST",
          signal: ctrl.signal,
          body: {
            quantity: Number(form.quantity), unit: form.unit,
            pickup_deadline: new Date(form.pickup_deadline).toISOString(), attested: true,
            description: form.description,
          },
        }),
        minWait,
      ]);
      if (ctrl.signal.aborted) return;
      setResult(res);
      if (res.matching.matched) {
        api<MatchingExplanation>(`/rescues/${res.rescue.id}/matching-explanation`).then(setExplanation).catch(() => undefined);
      }
      refresh();
    } catch (err) {
      if (isAbort(err) || ctrl.signal.aborted) {
        setFormError("Stopped waiting. If the server already received the rescue it will appear under Your rescues.");
        refresh();
      } else {
        await minWait;
        setFormError((err as Error).message);
      }
    } finally {
      if (pending.current === ctrl) pending.current = null;
      setFinding(false);
    }
  }

  function cancelFinding() {
    pending.current?.abort();
  }

  const active = rescues?.filter((r) => !["received", "cancelled", "expired", "rejected"].includes(r.status)) ?? [];
  const completed = rescues?.filter((r) => r.status === "received") ?? [];
  const mealsDonated = completed.reduce((sum, r) => sum + (r.quantities.received_meals ?? 0), 0);
  const latest = rescues?.find((r) => r.id === result?.rescue.id);
  const history = rescues?.filter((r) => r.id !== result?.rescue.id) ?? [];

  return (
    <AppShell icon="restaurant" title={result?.rescue.restaurant.name ?? "Restaurant"} subtitle="Post surplus food. FoodFlow finds a carrier and the organizations that need it."
      actions={<div className="flex flex-wrap items-center gap-2">
        <span className="chip">{user.name}</span>
        <LiveStatus updatedAt={updatedAt} error={error} />
      </div>}>
      <ErrorNote message={error} onRetry={refresh} stale={!!rescues} />
      {!rescues ? <Loading /> : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="Active rescues" icon="food-box" value={active.length} />
          <Stat label="Completed" icon="food-safe" value={completed.length} />
          <Stat label="Meals donated" icon="hot-meal" value={number(mealsDonated)} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <form className="panel flex flex-col gap-4 self-start" onSubmit={submit} aria-labelledby="create-title">
          <h2 id="create-title" style={{ fontSize: "var(--t-lg)" }}>Create Food Rescue</h2>
          <div className="grid grid-cols-2 gap-4">
            <label className="field"><span>Quantity</span><input className="input num" type="number" min={1} step="0.5" required value={form.quantity} onChange={set("quantity")} /></label>
            <label className="field"><span>Unit</span>
              <select className="input" value={form.unit} onChange={set("unit")}>
                {UNITS.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
              </select>
            </label>
          </div>
          <label className="field"><span>Pickup deadline</span><input className="input" type="datetime-local" required value={form.pickup_deadline} onChange={set("pickup_deadline")} /></label>
          <label className="field"><span>Description</span><textarea className="input" value={form.description} onChange={set("description")} /></label>
          <label className="flex items-start gap-3 rounded-lg border border-line p-3">
            <input type="checkbox" className="mt-1 h-5 w-5" checked={form.attested}
              onChange={(e) => setForm({ ...form, attested: e.target.checked })} />
            <span className="text-sm">This food was stored and handled safely (hot food kept hot, cold food kept cold) and is safe to eat.</span>
          </label>
          {formError && <div className="alert alert-bad" role="alert">{formError}</div>}
          <button className="btn btn-primary btn-lg" disabled={finding}>{finding ? "Finding a match..." : "Find a match"}</button>
        </form>

        <div className="flex min-w-0 flex-col gap-4" aria-live="polite">
          {finding && (
            <RescueSequence meals={Number(form.quantity) || 0} restaurantName={result?.rescue.restaurant.name ?? "your restaurant"} onCancel={cancelFinding} />
          )}
          {!finding && result && !result.matching.matched && (
            <>
              <div className="alert alert-info">Rescue posted. {result.matching.reason ?? "No carrier is free right now"}; FoodFlow will keep trying.</div>
              <RescueAreaMap rescue={result.rescue} />
            </>
          )}
          {!finding && latest && <PickupCode rescue={latest} />}
          {!finding && result?.matching.matched && latest && currentTrip(latest.trips) && (
            <MatchCard rescue={latest} trip={currentTrip(latest.trips)!} explanation={explanation} />
          )}
          {!finding && !result && <p className="panel text-ink-2">Post a rescue to see the match, the route, and why FoodFlow chose it.</p>}

          {history.length > 0 && (
            <section className="flex flex-col gap-3">
              <h3>Your rescues</h3>
              {history.map((r) => {
                const trip = currentTrip(r.trips);
                const isActive = trip && !["received", "cancelled", "rejected", "expired", "reassigned"].includes(trip.status);
                return isActive ? (
                  <section key={r.id} className="panel flex flex-col gap-4" aria-label={`Rescue #${r.id}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <strong>{r.est_meals} meals · {trip.carrier.type === "volunteer" ? trip.carrier.first_name : trip.carrier.label}</strong>
                      <span className="chip">pickup {until(r.pickup_deadline)}</span>
                    </div>
                    <PickupCode rescue={r} />
                    <div className="grid gap-4 md:grid-cols-[240px_1fr]">
                      <StatusTimeline trip={trip} />
                      <DeliveryMap rescue={r} trip={trip} height={280} />
                    </div>
                  </section>
                ) : (
                  <div key={r.id} className="panel panel-tight flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-col">
                      <strong>{r.est_meals} meals{r.description ? ` · ${r.description}` : ""}</strong>
                      <span className="text-sm text-ink-3">
                        Pickup by {clock(r.pickup_deadline)}{trip ? ` · ${trip.carrier.type === "volunteer" ? trip.carrier.first_name : trip.carrier.label}` : ""}
                      </span>
                    </div>
                    <span className={`chip ${r.status === "received" ? "chip-good" : ["expired", "rejected", "cancelled"].includes(r.status) ? "chip-bad" : ""}`}>{r.status}</span>
                  </div>
                );
              })}
            </section>
          )}
        </div>
      </div>
    </AppShell>
  );
}
