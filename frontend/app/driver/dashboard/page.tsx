"use client";
import { useState } from "react";
import AppShell, { ErrorNote, LiveStatus, Loading, Stat } from "@/components/AppShell";
import DeliveryMap from "@/components/DeliveryMap";
import FlowMap from "@/components/FlowMap";
import { matchMapProps } from "@/components/MatchCard";
import StatusTimeline from "@/components/StatusTimeline";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { clock, miles, minutes, nextStep, number, until } from "@/lib/format";
import type { DriverDashboard } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";
import { useShareLocation } from "@/lib/useShareLocation";

export default function DriverDashboardPage() {
  const user = useRequireRole("DRIVER");
  const { data, error, refresh, updatedAt } = usePoll<DriverDashboard>(user ? "/drivers/dashboard" : null);
  const [busy, setBusy] = useState(false);
  const [shareGps, setShareGps] = useState(false);
  const gps = useShareLocation(shareGps && !!user);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!user) return null;

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const offer = data?.offer;
  const active = data?.active_delivery;
  const step = active ? nextStep(active.status) : null;

  return (
    <AppShell
      title={data ? `Hi, ${data.driver.name}` : "Driver"}
      subtitle="One offer at a time, one next step at a time."
      actions={data && (
        <div className="flex flex-wrap items-center gap-2">
        <LiveStatus updatedAt={updatedAt} error={error} />
        <label className="panel panel-tight flex items-center gap-3">
          <input type="checkbox" role="switch" className="h-6 w-6" checked={shareGps} onChange={(e) => setShareGps(e.target.checked)}
            aria-label="Share live location" />
          <span className="flex flex-col">
            <span className="font-semibold">Share live location</span>
            <span className="text-xs text-ink-3">
              {gps.state === "sharing" ? "Sharing GPS" : gps.state === "waiting" ? gps.message : gps.state === "error" ? gps.message : "Off: position is estimated from the route"}
            </span>
          </span>
        </label>
        <label className="panel panel-tight flex items-center gap-3">
          <input type="checkbox" role="switch" className="h-6 w-6" checked={data.driver.is_available} disabled={busy || !!active}
            onChange={(e) => act(() => api("/drivers/me/availability", { method: "PATCH", body: { is_available: e.target.checked } }))}
            aria-label="Available for rescues" />
          <span className="font-semibold">{data.driver.is_available ? "Available" : active ? "On a delivery" : "Offline"}</span>
        </label>
        </div>
      )}
    >
      <ErrorNote message={actionError} />
      <ErrorNote message={error} onRetry={refresh} stale={!!data} />
      {!data ? <Loading /> : (
        <>
          {offer && (
            <section className="panel panel-accent flex flex-col gap-4" aria-labelledby="offer-title">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span id="offer-title" className="eyebrow" style={{ color: "var(--accent)" }}>New food rescue</span>
                <span className="chip chip-warn">pickup {until(offer.rescue.pickup_deadline)}</span>
              </div>
              <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
                <div className="flex flex-col gap-4">
                  <h2>{offer.rescue.meals} meals from {offer.rescue.restaurant_name}</h2>
                  <p className="text-ink-2">{offer.rescue.food_type}. Pick up by {clock(offer.rescue.pickup_deadline)}.</p>
                  <div className="flex flex-wrap gap-1">
                    <span className="chip">to pickup {miles(offer.match.pickup_miles)}</span>
                    <span className="chip">drop offs {miles(offer.match.dropoff_miles)}</span>
                    <span className="chip chip-accent">about {minutes(offer.match.eta_minutes)}</span>
                    {offer.match.eta_range_minutes && <span className="chip">likely {Math.round(offer.match.eta_range_minutes[0])} to {Math.round(offer.match.eta_range_minutes[1])} min</span>}
                  </div>
                  <ol className="transit" aria-label="Stops">
                    <li className="done"><span className="dot">P</span><span className="label">{offer.rescue.restaurant_name}</span></li>
                    {offer.match.stops.map((s, i) => (
                      <li key={i} className="now"><span className="dot">{i + 1}</span>
                        <span className="label flex justify-between gap-2">{s.name}<span className="chip">{s.meals} meals</span></span></li>
                    ))}
                  </ol>
                  <ul className="flex flex-col gap-1 text-sm text-ink-2">
                    {offer.match.reasons.map((r) => <li key={r}>{r}</li>)}
                  </ul>
                  <div className="grid grid-cols-2 gap-3">
                    <button className="btn btn-primary btn-lg" disabled={busy}
                      onClick={() => act(() => api(`/rescues/${offer.rescue.id}/accept`, { method: "POST" }))}>Accept</button>
                    <button className="btn btn-danger btn-lg" disabled={busy}
                      onClick={() => act(() => api(`/rescues/${offer.rescue.id}/decline`, { method: "POST" }))}>Decline</button>
                  </div>
                </div>
                <FlowMap {...matchMapProps(offer.match, offer.rescue)} height={360} />
              </div>
            </section>
          )}

          {active && (
            <section className="panel flex flex-col gap-4" aria-labelledby="active-title">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 id="active-title">Active delivery · {active.meals} meals</h2>
                <span className="chip">{active.restaurant.name}</span>
              </div>
              {step && (
                <button className="btn btn-primary btn-lg btn-block" style={{ minHeight: 64, fontSize: "var(--t-lg)" }} disabled={busy}
                  onClick={() => act(() => api(`/deliveries/${active.id}/status`, { method: "PATCH", body: { status: step.status } }))}>
                  {step.action}
                </button>
              )}
              <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
                <div className="flex flex-col gap-4">
                  <StatusTimeline delivery={active} />
                  <hr className="divider" />
                  <ol className="flex flex-col gap-2 text-sm">
                    <li><strong>Pickup:</strong> {active.restaurant.address || active.restaurant.name}</li>
                    {active.stops.map((s, i) => <li key={i}><strong>Stop {i + 1}:</strong> {s.name}, {s.meals} meals</li>)}
                  </ol>
                </div>
                <DeliveryMap delivery={active} height={380} />
              </div>
            </section>
          )}

          {!offer && !active && (
            <div className="panel flex flex-col gap-2">
              <h3>{data.driver.is_available ? "Waiting for the next rescue" : "You are offline"}</h3>
              <p className="text-ink-2">{data.driver.is_available
                ? "New offers appear here automatically. Keep this page open."
                : "Turn on availability to receive food rescue offers."}</p>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-[240px_1fr]">
            <Stat label="Meals moved" value={number(data.total_meals_moved)} note={`${data.completed.length} deliveries`} />
            <section className="panel flex flex-col gap-3">
              <h3>Completed deliveries</h3>
              {data.completed.length === 0 ? <p className="text-ink-3">None yet.</p> : (
                <ul className="flex flex-col divide-y divide-line">
                  {data.completed.map((d) => (
                    <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                      <span>{d.meals} meals · {d.restaurant.name} → {d.stops.map((s) => s.name).join(", ")}</span>
                      <span className={`chip ${d.status === "CONFIRMED" ? "chip-good" : ""}`}>{d.status === "CONFIRMED" ? "confirmed" : "awaiting confirmation"}{d.is_demo_seed ? " · demo" : ""}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </AppShell>
  );
}
