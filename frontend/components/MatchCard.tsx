"use client";
import FlowMap from "./FlowMap";
import WhyThisMatch from "./WhyThisMatch";
import { miles, minutes } from "@/lib/format";
import type { Match, Rescue } from "@/lib/types";

export function matchMapProps(match: Match, rescue: Pick<Rescue, "restaurant_name" | "lat" | "lng">) {
  return {
    restaurants: [{ id: "r", lat: rescue.lat, lng: rescue.lng, label: rescue.restaurant_name, detail: "Pickup" }],
    drivers: [{ id: `d${match.driver.id}`, lat: match.driver.lat, lng: match.driver.lng, label: match.driver.name, detail: "Matched driver" }],
    organizations: match.stops.map((s) => ({ id: `o${s.organization_id}`, lat: s.lat, lng: s.lng, label: s.name, detail: `${s.meals} meals` })),
    routes: [{
      id: `m${match.id ?? "new"}`,
      geometry: [[match.driver.lat, match.driver.lng], [rescue.lat, rescue.lng], ...match.stops.map((s) => [s.lat, s.lng] as [number, number])] as [number, number][],
      stops: match.stops.map((s) => ({ lat: s.lat, lng: s.lng, label: s.name })),
    }],
    chips: [miles(match.pickup_miles + match.dropoff_miles), `ETA ${minutes(match.eta_minutes)}`],
  };
}

export default function MatchCard({ match, rescue, showMap = true }: {
  match: Match; rescue: Pick<Rescue, "restaurant_name" | "lat" | "lng" | "meals">; showMap?: boolean;
}) {
  return (
    <section className="flex flex-col gap-4" aria-label="Match found">
      <div className="panel panel-accent flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="eyebrow" style={{ color: "var(--accent)" }}>Match found</span>
          <div className="flex flex-wrap gap-1">
            <span className="chip">Pickup {miles(match.pickup_miles)}</span>
            <span className="chip">Drop offs {miles(match.dropoff_miles)}</span>
            <span className="chip chip-accent">ETA {minutes(match.eta_minutes)}</span>
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-sm text-ink-3">Driver</span>
          <strong className="text-2xl" style={{ fontFamily: "var(--ff-display)" }}>{match.driver.name}</strong>
        </div>
        <ol className="transit" aria-label="Stops">
          <li className="done">
            <span className="dot">P</span>
            <span className="label">Pick up {rescue.meals} meals at {rescue.restaurant_name}</span>
          </li>
          {match.stops.map((s, i) => (
            <li key={`${s.organization_id}-${i}`} className="now">
              <span className="dot">{i + 1}</span>
              <span className="label flex flex-wrap justify-between gap-2">{s.name}<span className="chip">{s.meals} meals</span></span>
            </li>
          ))}
        </ol>
      </div>
      {showMap && <FlowMap {...matchMapProps(match, rescue)} height={320} />}
      <WhyThisMatch candidates={match.top_candidates} reasons={match.reasons} />
    </section>
  );
}
