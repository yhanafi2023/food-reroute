"use client";
import { useEffect, useRef, useState } from "react";
import AppShell, { ErrorNote, LiveStatus, Loading, Stat } from "@/components/AppShell";
import DeliveryMap from "@/components/DeliveryMap";
import MatchCard from "@/components/MatchCard";
import RescueSequence from "@/components/RescueSequence";
import StatusTimeline from "@/components/StatusTimeline";
import { api, isAbort } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { clock, defaultDeadline, number, until } from "@/lib/format";
import type { CreateRescueResponse, RescueDetail, RestaurantDashboard } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

const EMPTY = { food_type: "Rice, black beans and roast chicken", meals: "50", weight_lbs: "60", pickup_address: "",
  pickup_deadline: "", time_sensitivity: "MEDIUM", description: "Trays from dinner service, kept hot.", food_safety_confirmed: false };

export default function RestaurantDashboardPage() {
  const user = useRequireRole("RESTAURANT");
  const { data, error, refresh, updatedAt } = usePoll<RestaurantDashboard>(user ? "/restaurants/dashboard" : null);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  const [form, setForm] = useState(() => ({ ...EMPTY, pickup_deadline: defaultDeadline() }));
  const [finding, setFinding] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateRescueResponse | null>(null);

  if (!user) return null;

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!form.food_safety_confirmed) {
      setFormError("Please confirm the food was stored and handled safely.");
      return;
    }
    setFinding(true);
    setResult(null);
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
            food_type: form.food_type, meals: Number(form.meals), weight_lbs: Number(form.weight_lbs),
            pickup_address: form.pickup_address || undefined, pickup_deadline: new Date(form.pickup_deadline).toISOString(),
            time_sensitivity: form.time_sensitivity, description: form.description, food_safety_confirmed: true,
          },
        }),
        minWait,
      ]);
      if (ctrl.signal.aborted) return;
      setResult(res);
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

  const s = data?.stats;
  const latest: RescueDetail | undefined = data?.rescues.find((r) => r.rescue.id === result?.rescue.id);
  const history = data?.rescues.filter((r) => r.rescue.id !== result?.rescue.id) ?? [];

  return (
    <AppShell title={data?.restaurant.name ?? "Restaurant"} subtitle="Post surplus food. FoodFlow finds a driver and the organizations that need it."
      actions={<div className="flex flex-wrap items-center gap-2">
        <span className="chip">Fictional demo partner</span>
        <LiveStatus updatedAt={updatedAt} error={error} />
      </div>}>
      <ErrorNote message={error} onRetry={refresh} stale={!!data} />
      {!data ? <Loading /> : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="Active rescues" value={s!.active} />
          <Stat label="Completed" value={s!.completed} />
          <Stat label="Meals donated" value={number(s!.meals_donated)} />
          <Stat label="Lbs diverted" value={number(s!.lbs_diverted)} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <form className="panel flex flex-col gap-4 self-start" onSubmit={submit} aria-labelledby="create-title">
          <h2 id="create-title" style={{ fontSize: "var(--t-lg)" }}>Create Food Rescue</h2>
          <label className="field"><span>Food type</span><input className="input" required value={form.food_type} onChange={set("food_type")} /></label>
          <div className="grid grid-cols-2 gap-4">
            <label className="field"><span>Meals</span><input className="input num" type="number" min={1} required value={form.meals} onChange={set("meals")} /></label>
            <label className="field"><span>Weight (lbs)</span><input className="input num" type="number" min={0} step="0.5" required value={form.weight_lbs} onChange={set("weight_lbs")} /></label>
          </div>
          <label className="field"><span>Pickup address</span>
            <input className="input" placeholder={data?.restaurant.address ?? "Restaurant address"} value={form.pickup_address} onChange={set("pickup_address")} />
          </label>
          <label className="field"><span>Pickup deadline</span><input className="input" type="datetime-local" required value={form.pickup_deadline} onChange={set("pickup_deadline")} /></label>
          <label className="field"><span>Time sensitivity</span>
            <select className="input" value={form.time_sensitivity} onChange={set("time_sensitivity")}>
              <option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option>
            </select>
          </label>
          <label className="field"><span>Description</span><textarea className="input" value={form.description} onChange={set("description")} /></label>
          <label className="flex items-start gap-3 rounded-lg border border-line p-3">
            <input type="checkbox" className="mt-1 h-5 w-5" checked={form.food_safety_confirmed}
              onChange={(e) => setForm({ ...form, food_safety_confirmed: e.target.checked })} />
            <span className="text-sm">This food was stored and handled safely (hot food kept hot, cold food kept cold) and is safe to eat.</span>
          </label>
          {formError && <div className="alert alert-bad" role="alert">{formError}</div>}
          <button className="btn btn-primary btn-lg" disabled={finding}>{finding ? "Finding a match..." : "Find a match"}</button>
        </form>

        <div className="flex min-w-0 flex-col gap-4" aria-live="polite">
          {finding && (
            <RescueSequence meals={Number(form.meals) || 0} restaurantName={data?.restaurant.name ?? "your restaurant"} onCancel={cancelFinding} />
          )}
          {!finding && result && !result.match && (
            <div className="alert alert-info">Rescue posted. No driver is free right now; FoodFlow will keep trying and an admin can run matching.</div>
          )}
          {!finding && result?.match && !latest?.delivery && <MatchCard match={result.match} rescue={result.rescue} />}
          {!finding && latest?.delivery && <LiveDelivery item={latest} />}
          {!finding && !result && <p className="panel text-ink-2">Post a rescue to see the match, the route, and why FoodFlow chose it.</p>}

          {history.length > 0 && (
            <section className="flex flex-col gap-3">
              <h3>Your rescues</h3>
              {history.map((r) => (r.delivery && r.rescue.status !== "CONFIRMED" ? <LiveDelivery key={r.rescue.id} item={r} /> : (
                <div key={r.rescue.id} className="panel panel-tight flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-col">
                    <strong>{r.rescue.meals} meals · {r.rescue.food_type}</strong>
                    <span className="text-sm text-ink-3">Pickup by {clock(r.rescue.pickup_deadline)}{r.match ? ` · driver ${r.match.driver.name}` : ""}</span>
                  </div>
                  <span className={`chip ${r.rescue.status === "CONFIRMED" ? "chip-good" : r.rescue.status === "EXPIRED" ? "chip-bad" : ""}`}>{r.rescue.status}</span>
                </div>
              )))}
            </section>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function LiveDelivery({ item }: { item: RescueDetail }) {
  const d = item.delivery!;
  return (
    <section className="panel flex flex-col gap-4" aria-label={`Delivery for ${item.rescue.meals} meals`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong>{item.rescue.meals} meals · driver {d.driver_name}</strong>
        <span className="chip">pickup {until(item.rescue.pickup_deadline)}</span>
      </div>
      <div className="grid gap-4 md:grid-cols-[240px_1fr]">
        <StatusTimeline delivery={d} />
        <DeliveryMap delivery={d} height={280} />
      </div>
    </section>
  );
}
