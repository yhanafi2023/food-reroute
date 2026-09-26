"use client";
import { CARRIER_LABEL, minutesBetween, qty, relative, statusLabel, time } from "@/lib/format";
import type { Rescue, Trip } from "@/lib/types";

const STEPS: { key: string; label: string }[] = [
  { key: "posted", label: "Posted" },
  { key: "matched", label: "Carrier assigned" },
  { key: "en_route_pickup", label: "On the way to pick up" },
  { key: "en_route_dropoff", label: "Picked up, on the way" },
  { key: "delivered", label: "Delivered" },
  { key: "received", label: "Confirmed received" },
];
const ORDER = STEPS.map((s) => s.key);

export function stepIndex(status: string): number {
  if (status === "picked_up") return ORDER.indexOf("en_route_dropoff");
  return ORDER.indexOf(status);
}

export function StatusSteps({ status }: { status: string }) {
  const at = stepIndex(status);
  if (at < 0) return <p className="chip chip-bad">{statusLabel(status)}</p>;
  return (
    <ol className="transit" aria-label="Donation progress">
      {STEPS.map((s, i) => (
        <li key={s.key} className={i < at || (i === at && s.key === "received") ? "done" : i === at ? "now" : ""} aria-current={i === at ? "step" : undefined}>
          <span className="dot" aria-hidden="true">
            {i + 1}
          </span>
          <span className="label">{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

export function activeTrip(r: Rescue): Trip | undefined {
  return r.trips.find((t) => !["cancelled", "reassigned", "expired"].includes(t.status)) ?? r.trips[r.trips.length - 1];
}

export function CarrierLine({ trip }: { trip: Trip }) {
  const c = trip.carrier;
  return (
    <span>
      {c.type === "volunteer" ? (
        <>
          <strong>{c.first_name}</strong> (volunteer{c.vehicle ? `, ${c.vehicle}` : ""})
        </>
      ) : (
        <>
          <strong>{CARRIER_LABEL[c.type]}</strong> {c.vehicle_id ? `(${c.vehicle_id})` : ""}{" "}
          <span className="chip chip-warn">Simulated</span>
        </>
      )}
    </span>
  );
}

// >=20 min of slack: comfortable. 10-19: tight but workable. Under 10: at risk. (Thresholds from 238b63d.)
function marginClass(margin: number) {
  if (margin >= 20) return "is-good";
  if (margin >= 10) return "is-warn";
  return "is-bad";
}

// Pickup ETA, time left before the pickup deadline, and the slack between them, from the rescue's recorded times.
function MetricRow({ rescue, etaPickup, now }: { rescue: Rescue; etaPickup: string; now: string }) {
  const eta = Math.max(0, minutesBetween(now, etaPickup));
  const deadline = Math.max(0, minutesBetween(now, rescue.pickup_deadline));
  const margin = minutesBetween(etaPickup, rescue.pickup_deadline);
  return (
    <div className="match-metric-row">
      <div className="match-metric">
        <span className="eyebrow">Pickup ETA</span>
        <span className="match-metric-value">
          {eta}
          <span className="text-sm font-semibold text-ink-3"> min</span>
        </span>
      </div>
      <div className="match-metric">
        <span className="eyebrow">Pickup deadline</span>
        <span className="match-metric-value">
          {deadline}
          <span className="text-sm font-semibold text-ink-3"> min</span>
        </span>
      </div>
      <div className={`match-metric ${marginClass(margin)}`}>
        <span className="eyebrow">Safety margin</span>
        <span className="match-metric-value">
          {margin}
          <span className="text-sm font-semibold text-ink-3"> min</span>
        </span>
      </div>
    </div>
  );
}

export function RescueCard({ rescue, now, showCode = true }: { rescue: Rescue; now: string | null; showCode?: boolean }) {
  const trip = activeTrip(rescue);
  const beforePickup = ["posted", "matched", "en_route_pickup"].includes(rescue.status);
  return (
    <article className="panel stack match-card-enter" aria-label={`Donation ${rescue.id}`} data-testid={`rescue-${rescue.id}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>
          {qty(rescue.quantity, rescue.unit)} ({rescue.est_meals} meals est.)
        </h3>
        <span className="chip" data-testid="rescue-status">
          {statusLabel(rescue.status)}
        </span>
      </div>
      <p className="small muted">
        #{rescue.id} · {rescue.category.replace("_", " ")} · pickup by {time(rescue.pickup_deadline)} ({relative(rescue.pickup_deadline, now)})
      </p>
      {showCode && rescue.pickup_code && beforePickup ? (
        <div className="panel panel-tight stack" style={{ background: "var(--wash)", gap: "var(--s-1)" }}>
          <span className="eyebrow">Pickup code: tell the driver at handoff</span>
          <span className="code-big" data-testid="pickup-code">
            {rescue.pickup_code}
          </span>
        </div>
      ) : null}
      {trip && !["cancelled", "reassigned", "expired"].includes(trip.status) ? (
        <>
          <div className="match-flow" aria-label="Route">
            <div className="match-flow-node is-restaurant">
              <span className="match-flow-icon" aria-hidden="true">
                🍽️
              </span>
              <div className="match-flow-body">
                <span className="match-flow-name uppercase">{rescue.restaurant.name}</span>
                <span className="chip">Pickup{trip.eta_pickup && beforePickup ? ` ${time(trip.eta_pickup)}` : ""}</span>
              </div>
            </div>
            <div className="match-flow-arrow" aria-hidden="true" />
            <div className="match-flow-node is-driver">
              <span className="match-flow-icon" aria-hidden="true">
                🚗
              </span>
              <div className="match-flow-body">
                <CarrierLine trip={trip} />
                <span className="chip chip-accent">{statusLabel(trip.status)}</span>
              </div>
            </div>
            {trip.stops.map((s) => (
              <div key={s.id}>
                <div className="match-flow-arrow" aria-hidden="true" />
                <div className="match-flow-node is-org">
                  <span className="match-flow-icon" aria-hidden="true">
                    🏢
                  </span>
                  <div className="match-flow-body">
                    <span className="match-flow-name">{s.organization.name}</span>
                    <span className="chip chip-good">
                      {s.allocated_meals} meals · {statusLabel(s.status)}
                      {s.received_meals != null ? `, ${s.received_meals} accepted` : ""}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
          {beforePickup && trip.eta_pickup && now ? <MetricRow rescue={rescue} etaPickup={trip.eta_pickup} now={now} /> : null}
        </>
      ) : rescue.status === "posted" ? (
        <p className="alert alert-info">No carrier yet. FoodFlow retries every 2 minutes and tells you when one is assigned.</p>
      ) : null}
      <StatusSteps status={rescue.status} />
    </article>
  );
}
