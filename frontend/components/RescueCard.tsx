"use client";
import { CARRIER_LABEL, qty, relative, statusLabel, time } from "@/lib/format";
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

export function RescueCard({ rescue, now, showCode = true }: { rescue: Rescue; now: string | null; showCode?: boolean }) {
  const trip = activeTrip(rescue);
  const beforePickup = ["posted", "matched", "en_route_pickup"].includes(rescue.status);
  return (
    <article className="panel stack" aria-label={`Donation ${rescue.id}`} data-testid={`rescue-${rescue.id}`}>
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
        <div className="stack" style={{ gap: "var(--s-2)" }}>
          <p>
            <CarrierLine trip={trip} />
            {trip.eta_pickup && beforePickup ? (
              <>
                , pickup around <strong>{time(trip.eta_pickup)}</strong>
              </>
            ) : null}
          </p>
          <ul className="small" aria-label="Drop offs" style={{ paddingLeft: "var(--s-5)", margin: 0 }}>
            {trip.stops.map((s) => (
              <li key={s.id}>
                {s.allocated_meals} meals to {s.organization.name}: {statusLabel(s.status)}
                {s.received_meals != null ? `, ${s.received_meals} accepted` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : rescue.status === "posted" ? (
        <p className="alert alert-info">No carrier yet. FoodFlow retries every 2 minutes and tells you when one is assigned.</p>
      ) : null}
      <StatusSteps status={rescue.status} />
    </article>
  );
}
