"use client";
import FlowMap from "./FlowMap";
import { clock, miles, minutes } from "@/lib/format";
import type { Delivery, Tracking } from "@/lib/types";
import { useTracking } from "@/lib/useTracking";

const SOURCE_TEXT: Record<Tracking["driver"]["position_source"], string> = {
  gps: "live GPS",
  estimated: "estimated position",
  status: "at a stop",
};

export function deliveryMapProps(d: Delivery, t?: Tracking | null) {
  const pos = t?.driver.position ?? d.driver_location;
  return {
    restaurants: [{ id: `r${d.restaurant.id}`, lat: d.restaurant.lat, lng: d.restaurant.lng, label: d.restaurant.name, detail: "Pickup" }],
    drivers: [{
      id: `d${d.driver_id}`, lat: pos.lat, lng: pos.lng, label: d.driver_name,
      detail: t ? `${SOURCE_TEXT[t.driver.position_source]}` : d.status.replace(/_/g, " ").toLowerCase(),
    }],
    organizations: d.stops.map((s) => ({ id: `o${s.organization_id}`, lat: s.lat, lng: s.lng, label: s.name, detail: `${s.meals} meals` })),
    routes: [{ id: `del${d.id}`, geometry: d.route.geometry, stops: d.stops.map((s) => ({ lat: s.lat, lng: s.lng, label: s.name })) }],
    chips: [
      miles(d.route.distance_miles),
      t?.eta ? `ETA ${minutes(t.eta.p50)}` : `ETA ${minutes(d.route.ml_eta_minutes ?? d.route.eta_minutes)}`,
      d.route.source === "offline" ? "straight-line route" : `${d.route.source} road route`,
    ],
  };
}

// ETA to the viewer's own location (pickup for the restaurant, their stop for an organization).
export function LiveEta({ tracking }: { tracking: Tracking | null }) {
  if (!tracking) return <div className="skeleton h-16" aria-hidden />;
  const { eta, driver, target, note } = tracking;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-wash p-4" aria-live="polite">
      <div className="flex flex-col gap-1">
        <span className="eyebrow">{target.kind === "pickup" ? "Driver to pickup" : `Driver to ${target.name}`}</span>
        {eta ? (
          <span className="text-xl font-bold" style={{ fontFamily: "var(--ff-display)" }}>
            About {Math.round(eta.p50)} min <span className="text-base font-semibold text-ink-2">· likely {Math.round(eta.p10)} to {Math.round(eta.p90)} min · around {clock(eta.arrival_at)}</span>
          </span>
        ) : (
          <span className="text-xl font-bold" style={{ fontFamily: "var(--ff-display)" }}>{note}</span>
        )}
      </div>
      <div className="flex flex-col items-end gap-1 text-right">
        <span className={`chip ${driver.position_source === "gps" ? "chip-good" : ""}`}>{driver.name}: {SOURCE_TEXT[driver.position_source]}</span>
        <span className="text-xs text-ink-3">{eta?.source === "ml" ? "ML ETA from real road-network data, no live traffic" : eta ? "Rule-of-thumb ETA" : ""}</span>
      </div>
    </div>
  );
}

export default function DeliveryMap({ delivery, height = 340, withEta = true }: { delivery: Delivery; height?: number; withEta?: boolean }) {
  const moving = !["DELIVERED", "CONFIRMED"].includes(delivery.status);
  const { data: tracking } = useTracking(delivery.id, moving);
  return (
    <div className="flex flex-col gap-3">
      {withEta && moving && <LiveEta tracking={tracking} />}
      <FlowMap {...deliveryMapProps(delivery, tracking)} height={height} fitKey={`del${delivery.id}`} />
    </div>
  );
}
