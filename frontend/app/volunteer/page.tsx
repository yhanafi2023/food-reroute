"use client";
import { useEffect, useRef, useState } from "react";
import RescueMap from "@/components/RescueMap";
import { CarrierLine } from "@/components/RescueCard";
import { Shell } from "@/components/Shell";
import { Empty, ErrorNote, Loading } from "@/components/States";
import { api, newIdempotencyKey } from "@/lib/api";
import { useWorkspace } from "@/lib/auth";
import { relative, statusLabel, time } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";
import { useServerNow } from "@/lib/useServerNow";
import { useShareLocation } from "@/lib/useShareLocation";
import type { Rescue, Stop, Trip, VolunteerTrips } from "@/lib/types";

// One key per intended action and body: a retried tap on bad signal replays instead of applying twice,
// while a corrected code is a new request (the server rejects a reused key with a different body).
function useActionKey() {
  const keys = useRef(new Map<string, string>());
  return {
    get(action: string) {
      if (!keys.current.has(action)) keys.current.set(action, newIdempotencyKey());
      return keys.current.get(action)!;
    },
    done(action: string) {
      keys.current.delete(action);
    },
  };
}

function CodeForm({
  label,
  help,
  submitLabel,
  withMeals,
  defaultMeals,
  onSubmit,
}: {
  label: string;
  help: string;
  submitLabel: string;
  withMeals?: boolean;
  defaultMeals?: number;
  onSubmit: (code: string, meals: number) => Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [meals, setMeals] = useState(defaultMeals ?? 1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          await onSubmit(code, meals);
          setCode("");
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {error ? <ErrorNote message={error} /> : null}
      <label className="field">
        <span>{label}</span>
        <input
          className="input code-big"
          style={{ fontSize: 28 }}
          inputMode="numeric"
          autoComplete="off"
          maxLength={8}
          required
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\s/g, ""))}
        />
        <span className="small muted">{help}</span>
      </label>
      {withMeals ? (
        <label className="field">
          <span>Meals picked up</span>
          <input className="input" type="number" min={1} max={5000} required value={meals} onChange={(e) => setMeals(Number(e.target.value) || 1)} />
        </label>
      ) : null}
      <button type="submit" className="btn btn-good btn-lg" disabled={busy || code.length < 4}>
        {busy ? "Checking" : submitLabel}
      </button>
    </form>
  );
}

function mapsLink(lat: number, lng: number) {
  return `https://www.openstreetmap.org/directions?to=${lat}%2C${lng}`;
}

function StopBlock({ stop, trip, onChanged, keys }: { stop: Stop; trip: Trip; onChanged: () => void; keys: ReturnType<typeof useActionKey> }) {
  const [closedBusy, setClosedBusy] = useState(false);
  const [note, setNote] = useState("");
  const current = trip.status === "en_route_dropoff" && stop.status === "pending";
  return (
    <div className="panel panel-tight stack" aria-label={`Drop off at ${stop.organization.name}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong>
          Drop off {stop.seq}: {stop.allocated_meals} meals to {stop.organization.name}
        </strong>
        <span className="chip">{statusLabel(stop.status)}</span>
      </div>
      <p className="small muted">
        {stop.organization.address}
        {stop.eta ? ` · arrive around ${time(stop.eta)}` : ""}
      </p>
      {stop.receiving_instructions ? <p className="small">{stop.receiving_instructions}</p> : null}
      {stop.curb_location ? <p className="small">Curb: {stop.curb_location}</p> : null}
      {current ? (
        <>
          <a className="btn btn-ghost" href={mapsLink(stop.organization.lat, stop.organization.lng)} target="_blank" rel="noreferrer">
            Directions (OpenStreetMap)
          </a>
          <CodeForm
            label="Drop-off code"
            help="Ask the receiving staff for the code on their screen."
            submitLabel="Confirm drop off"
            onSubmit={async (code) => {
              await api(`/stops/${stop.id}/deliver`, { method: "POST", body: { code }, idempotencyKey: keys.get(`deliver-${stop.id}-${code}`) });
              keys.done(`deliver-${stop.id}-${code}`);
              onChanged();
            }}
          />
          <button
            type="button"
            className="btn btn-danger"
            disabled={closedBusy}
            onClick={async () => {
              setClosedBusy(true);
              try {
                const res = await api<{ rerouted_to: Stop | null }>(`/stops/${stop.id}/report-closed`, { method: "POST", body: { reason: "closed" } });
                setNote(res.rerouted_to ? `Re-routed to ${res.rerouted_to.organization.name}.` : "No other organization can take it right now; the coordinator was told.");
                onChanged();
              } catch (e) {
                setNote((e as Error).message);
              } finally {
                setClosedBusy(false);
              }
            }}
          >
            They are closed or full
          </button>
          {note ? <p role="status">{note}</p> : null}
        </>
      ) : null}
    </div>
  );
}

// The trip's pickup and drop offs on the map (GET /rescues/{id} is allowed for the volunteer on this trip).
function TripMap({ trip }: { trip: Trip }) {
  const [rescue, setRescue] = useState<Rescue | null>(null);
  useEffect(() => {
    let stopped = false;
    api<Rescue>(`/rescues/${trip.rescue_id}`)
      .then((r) => !stopped && setRescue(r))
      .catch(() => {});
    return () => {
      stopped = true;
    };
  }, [trip.rescue_id, trip.status]);
  return rescue ? <RescueMap rescues={[rescue]} height={240} /> : null;
}

function TripCard({ trip, now, onChanged }: { trip: Trip; now: string | null; onChanged: () => void }) {
  const keys = useActionKey();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const meals = trip.stops.reduce((n, s) => n + s.allocated_meals, 0);
  const restaurantStopLabel = `${meals} meals, pickup at ${time(trip.eta_pickup)}`;

  const act = async (path: string, key?: string) => {
    setBusy(true);
    setError("");
    try {
      await api(path, { method: "POST", body: {}, idempotencyKey: key ? keys.get(key) : undefined });
      if (key) keys.done(key);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="panel stack" aria-label={`Trip ${trip.id}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>{trip.status === "matched" ? "New rescue offer" : statusLabel(trip.status)}</h3>
        <span className="chip">Trip #{trip.id}</span>
      </div>
      <p>
        {restaurantStopLabel} ({relative(trip.eta_pickup, now)})
      </p>
      <p className="small muted">{trip.mode_reason}</p>
      <TripMap trip={trip} />
      {error ? <ErrorNote message={error} /> : null}
      {trip.status === "matched" ? (
        <div className="row">
          <button type="button" className="btn btn-primary btn-lg" disabled={busy} onClick={() => act(`/trips/${trip.id}/accept`, `accept-${trip.id}`)}>
            Accept
          </button>
          <button type="button" className="btn btn-ghost btn-lg" disabled={busy} onClick={() => act(`/trips/${trip.id}/decline`)}>
            Decline
          </button>
        </div>
      ) : null}
      {trip.status === "en_route_pickup" ? (
        <div className="stack">
          <CodeForm
            label="Pickup code"
            help="Ask the restaurant staff for the code on their screen."
            submitLabel="Confirm pickup"
            withMeals
            defaultMeals={meals}
            onSubmit={async (code, picked) => {
              await api(`/trips/${trip.id}/pickup`, {
                method: "POST",
                body: { code, picked_up_meals: picked },
                idempotencyKey: keys.get(`pickup-${trip.id}-${code}-${picked}`),
              });
              keys.done(`pickup-${trip.id}-${code}-${picked}`);
              onChanged();
            }}
          />
          <button type="button" className="btn btn-danger" disabled={busy} onClick={() => act(`/trips/${trip.id}/cancel`)}>
            I can&apos;t make it
          </button>
        </div>
      ) : null}
      {trip.status !== "matched"
        ? trip.stops.map((s) => <StopBlock key={s.id} stop={s} trip={trip} onChanged={onChanged} keys={keys} />)
        : trip.stops.map((s) => (
            <p key={s.id} className="small">
              Then {s.allocated_meals} meals to {s.organization.name}
            </p>
          ))}
      {trip.status === "delivered" ? <p className="alert alert-good">Delivered. The organization will confirm what it accepted.</p> : null}
    </article>
  );
}

// Opt-in GPS sharing while on a run (PATCH /volunteers/me/location), ported from a073982.
// Only admins ever see a volunteer's location; restaurants and organizations never do.
function ShareLocation({ active }: { active: boolean }) {
  const [on, setOn] = useState(false);
  const gps = useShareLocation(on && active);
  return (
    <div className="panel panel-tight row" style={{ justifyContent: "space-between" }}>
      <label className="row" style={{ flexWrap: "nowrap", gap: "var(--s-3)", minHeight: 44 }}>
        <input type="checkbox" role="switch" checked={on} onChange={(e) => setOn(e.target.checked)} style={{ width: 24, height: 24, flex: "none" }} />
        <span>Share my location while I am on a run</span>
      </label>
      <span className="small muted" role="status">
        {!on ? "Off" : !active ? "Starts when you accept a run" : gps.state === "sharing" ? "Sharing" : gps.message ?? gps.state}
      </span>
    </div>
  );
}

export default function VolunteerPage() {
  const user = useWorkspace("volunteer");
  const now = useServerNow();
  const { data, error, refresh } = usePoll<VolunteerTrips>(user ? "/volunteers/me/trips" : null, 3000);
  if (!user) return null;
  return (
    <Shell workspace="volunteer">
      <h1>Hi {user.first_name}</h1>
      {error && !data ? <ErrorNote message={error} onRetry={refresh} /> : null}
      {!data && !error ? <Loading label="Loading your trips" /> : null}
      {data ? (
        <div className="grid-2" style={{ alignItems: "start" }}>
          <section className="stack" aria-labelledby="now">
            <h2 id="now">Now</h2>
            <ShareLocation active={data.active.length > 0} />
            {data.offers.length + data.active.length === 0 ? (
              <Empty title="No rescues for you right now">New offers show up here. Keep this page open.</Empty>
            ) : null}
            {[...data.offers, ...data.active].map((t) => (
              <TripCard key={t.id} trip={t} now={now} onChanged={refresh} />
            ))}
          </section>
          <section className="stack" aria-labelledby="done">
            <h2 id="done">Finished</h2>
            {data.history.length === 0 ? <p className="muted">No finished trips yet.</p> : null}
            <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.history.slice(0, 10).map((t) => (
                <li key={t.id} className="panel panel-tight">
                  <CarrierLine trip={t} /> · trip #{t.id} · {statusLabel(t.status)} · {t.picked_up_meals ?? 0} meals
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}
    </Shell>
  );
}
