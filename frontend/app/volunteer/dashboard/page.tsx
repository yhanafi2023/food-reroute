"use client";
import { useEffect, useState } from "react";
import AppShell, { ErrorNote, LiveStatus, Loading, Stat } from "@/components/AppShell";
import DeliveryMap from "@/components/DeliveryMap";
import Icon from "@/components/Icon";
import StatusTimeline from "@/components/StatusTimeline";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { clock, number, until } from "@/lib/format";
import type { Rescue, Trip, VolunteerTrips } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";
import { useShareLocation } from "@/lib/useShareLocation";

// Trips don't carry their parent rescue (restaurant name, meals, deadline) inline,
// so the offer/active cards fetch it once per rescue id.
function useRescue(rescueId: number | undefined) {
  const [rescue, setRescue] = useState<Rescue | null>(null);
  useEffect(() => {
    if (!rescueId) return;
    let cancelled = false;
    api<Rescue>(`/rescues/${rescueId}`).then((r) => { if (!cancelled) setRescue(r); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [rescueId]);
  return rescueId && rescue?.id === rescueId ? rescue : null;
}

function OfferCard({ trip, busy, onAccept, onDecline }: { trip: Trip; busy: boolean; onAccept: () => void; onDecline: () => void }) {
  const rescue = useRescue(trip.rescue_id);
  if (!rescue) return <div className="skeleton h-40" aria-hidden />;
  return (
    <section className="panel panel-accent flex flex-col gap-4" aria-labelledby="offer-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span id="offer-title" className="eyebrow flex items-center gap-2" style={{ color: "var(--accent)" }}><Icon name="food-box" size={24} />New food rescue</span>
        <span className="chip chip-warn">pickup {until(rescue.pickup_deadline)}</span>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div className="flex flex-col gap-4">
          <h2>{rescue.est_meals} meals from {rescue.restaurant.name}</h2>
          <p className="text-ink-2">{rescue.category.replace("_", "-")} food. Pick up by {clock(rescue.pickup_deadline)}.</p>
          <ol className="transit" aria-label="Stops">
            <li className="done"><span className="dot">P</span><span className="label">{rescue.restaurant.name}</span></li>
            {trip.stops.map((s, i) => (
              <li key={s.id} className="now"><span className="dot">{i + 1}</span>
                <span className="label flex justify-between gap-2">{s.organization.name}<span className="chip">{s.allocated_meals} meals</span></span></li>
            ))}
          </ol>
          <p className="text-sm text-ink-2">{trip.mode_reason}</p>
          <div className="grid grid-cols-2 gap-3">
            <button className="btn btn-primary btn-lg" disabled={busy} onClick={onAccept}>Accept</button>
            <button className="btn btn-danger btn-lg" disabled={busy} onClick={onDecline}>Decline</button>
          </div>
        </div>
        <DeliveryMap rescue={rescue} trip={trip} height={360} />
      </div>
    </section>
  );
}

function PickupForm({ busy, onSubmit }: { busy: boolean; onSubmit: (code: string, meals: number) => void }) {
  const [code, setCode] = useState("");
  const [meals, setMeals] = useState("");
  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); onSubmit(code, Number(meals)); }}>
      <p className="text-ink-2">Ask the restaurant for the pickup code.</p>
      <div className="grid grid-cols-2 gap-3">
        <label className="field"><span>Pickup code</span><input className="input mono" required value={code} onChange={(e) => setCode(e.target.value)} /></label>
        <label className="field"><span>Meals picked up</span><input className="input num" type="number" min={1} required value={meals} onChange={(e) => setMeals(e.target.value)} /></label>
      </div>
      <button className="btn btn-primary btn-lg btn-block" style={{ minHeight: 64, fontSize: "var(--t-lg)" }} disabled={busy}>I picked up the food</button>
    </form>
  );
}

function DeliverForm({ stopId, orgName, busy, onSubmit }: { stopId: number; orgName: string; busy: boolean; onSubmit: (stopId: number, code: string) => void }) {
  const [code, setCode] = useState("");
  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); onSubmit(stopId, code); }}>
      <p className="text-ink-2">Ask {orgName} for the drop-off code.</p>
      <label className="field"><span>Drop-off code</span><input className="input mono" required value={code} onChange={(e) => setCode(e.target.value)} /></label>
      <button className="btn btn-primary btn-lg btn-block" style={{ minHeight: 64, fontSize: "var(--t-lg)" }} disabled={busy}>Delivered to {orgName}</button>
    </form>
  );
}

function ActiveTrip({ trip, busy, onPickup, onDeliver }: {
  trip: Trip; busy: boolean; onPickup: (code: string, meals: number) => void; onDeliver: (stopId: number, code: string) => void;
}) {
  const rescue = useRescue(trip.rescue_id);
  const nextStop = trip.stops.find((s) => s.status === "pending");
  return (
    <section className="panel flex flex-col gap-4" aria-labelledby="active-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="active-title">Active trip{rescue ? ` · ${rescue.est_meals} meals` : ""}</h2>
        {rescue && <span className="chip">{rescue.restaurant.name}</span>}
      </div>
      {trip.status === "en_route_pickup" && <PickupForm busy={busy} onSubmit={onPickup} />}
      {trip.status === "picked_up" && nextStop && (
        <p className="alert alert-info">Head to {nextStop.organization.name} to start delivering.</p>
      )}
      {trip.status === "en_route_dropoff" && nextStop && (
        <DeliverForm stopId={nextStop.id} orgName={nextStop.organization.name} busy={busy} onSubmit={onDeliver} />
      )}
      {trip.status === "delivered" && <p className="alert alert-good">Delivered. Waiting for the organization to confirm receipt.</p>}
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <div className="flex flex-col gap-4">
          <StatusTimeline trip={trip} />
          <hr className="divider" />
          {rescue && (
            <ol className="flex flex-col gap-2 text-sm">
              <li><strong>Pickup:</strong> {rescue.restaurant.address || rescue.restaurant.name}</li>
              {trip.stops.map((s, i) => <li key={s.id}><strong>Stop {i + 1}:</strong> {s.organization.name}, {s.allocated_meals} meals</li>)}
            </ol>
          )}
        </div>
        {rescue && <DeliveryMap rescue={rescue} trip={trip} height={380} />}
      </div>
    </section>
  );
}

export default function VolunteerDashboardPage() {
  const user = useRequireRole("volunteer");
  const { data, error, refresh, updatedAt } = usePoll<VolunteerTrips>(user ? "/volunteers/me/trips" : null);
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

  const offer = data?.offers[0];
  const active = data?.active[0];
  const totalMeals = data?.history.reduce((sum, t) => sum + (t.picked_up_meals ?? 0), 0) ?? 0;

  return (
    <AppShell
      icon="driver"
      title={`Hi, ${user.first_name}`}
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
                {gps.state === "sharing" ? "Sharing GPS" : gps.state === "waiting" ? gps.message : gps.state === "error" ? gps.message : "Off"}
              </span>
            </span>
          </label>
        </div>
      )}
    >
      <ErrorNote message={actionError} />
      <ErrorNote message={error} onRetry={refresh} stale={!!data} />
      {!data ? <Loading /> : (
        <>
          {offer && (
            <OfferCard trip={offer} busy={busy}
              onAccept={() => act(() => api(`/trips/${offer.id}/accept`, { method: "POST" }))}
              onDecline={() => act(() => api(`/trips/${offer.id}/decline`, { method: "POST" }))} />
          )}

          {active && (
            <ActiveTrip trip={active} busy={busy}
              onPickup={(code, meals) => act(() => api(`/trips/${active.id}/pickup`, { method: "POST", body: { code, picked_up_meals: meals } }))}
              onDeliver={(stopId, code) => act(() => api(`/stops/${stopId}/deliver`, { method: "POST", body: { code } }))} />
          )}

          {!offer && !active && (
            <div className="panel flex flex-col gap-2">
              <h3 className="flex items-center gap-3"><Icon name="schedule" size={30} />Waiting for the next rescue</h3>
              <p className="text-ink-2">New offers appear here automatically, based on your availability schedule. Keep this page open.</p>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-[240px_1fr]">
            <Stat label="Meals moved" icon="hot-meal" value={number(totalMeals)} note={`${data.history.length} trips`} />
            <section className="panel flex flex-col gap-3">
              <h3>Trip history</h3>
              {data.history.length === 0 ? <p className="text-ink-3">None yet.</p> : (
                <ul className="flex flex-col divide-y divide-line">
                  {data.history.map((t) => (
                    <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                      <span>{t.picked_up_meals ?? "?"} meals · {t.stops.map((s) => s.organization.name).join(", ")}</span>
                      <span className={`chip ${t.status === "received" ? "chip-good" : t.status === "rejected" ? "chip-bad" : ""}`}>{t.status}</span>
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
