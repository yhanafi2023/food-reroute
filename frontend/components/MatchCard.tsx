"use client";
import FlowMap from "./FlowMap";
import WhyThisMatch from "./WhyThisMatch";
import { miles, minutes, minutesUntil } from "@/lib/format";
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

// >=20 min of slack: comfortable. 10-19: tight but workable. Under 10 (or negative): at risk.
function marginClass(margin: number) {
  if (margin >= 20) return "is-good";
  if (margin >= 10) return "is-warn";
  return "is-bad";
}

export default function MatchCard({ match, rescue, showMap = true }: {
  match: Match; rescue: Pick<Rescue, "restaurant_name" | "lat" | "lng" | "meals" | "pickup_deadline">; showMap?: boolean;
}) {
  const foodDeadline = Math.max(0, minutesUntil(rescue.pickup_deadline));
  const pickupEta = match.pickup_eta_minutes ?? match.eta_minutes;
  const safetyMargin = Math.round(foodDeadline - pickupEta);
  const singleStop = match.stops.length === 1;

  return (
    <section className="flex flex-col gap-4 match-card-enter" aria-label="Match found">
      <div className="panel panel-accent flex flex-col gap-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="eyebrow inline-flex items-center gap-2" style={{ color: "var(--good)" }}>
            <i aria-hidden className="inline-block h-2 w-2 rounded-full bg-good" />
            Match found
          </span>
          {match.eta_range_minutes && (
            <span className="chip" title={match.eta_source === "ml" ? "ML ETA from real road-network data (OSRM, OpenStreetMap), no live traffic" : "Rule-of-thumb ETA"}>
              likely {Math.round(match.eta_range_minutes[0])} to {Math.round(match.eta_range_minutes[1])} min
            </span>
          )}
        </div>

        <div className="flex items-baseline gap-2">
          <span className="stat-value" style={{ fontSize: "var(--t-3xl)" }}>{rescue.meals}</span>
          <span className="eyebrow">Meals</span>
        </div>

        <div className="match-flow" aria-label="Route">
          <div className="match-flow-node is-restaurant">
            <span className="match-flow-icon" aria-hidden>🍽️</span>
            <div className="match-flow-body">
              <span className="match-flow-name uppercase">{rescue.restaurant_name}</span>
              <span className="chip">Pickup</span>
            </div>
          </div>
          <div className="match-flow-arrow" aria-hidden />
          <div className="match-flow-node is-driver">
            <span className="match-flow-icon" aria-hidden>🚗</span>
            <div className="match-flow-body">
              <span className="match-flow-name">{match.driver.name}</span>
              <span className="chip chip-accent">{miles(match.pickup_miles)} away</span>
            </div>
          </div>
          {match.stops.map((s, i) => (
            <div key={`${s.organization_id}-${i}`}>
              <div className="match-flow-arrow" aria-hidden />
              <div className="match-flow-node is-org">
                <span className="match-flow-icon" aria-hidden>🏢</span>
                <div className="match-flow-body">
                  <span className="match-flow-name">{s.name}</span>
                  <span className="chip chip-good">{s.meals} meals{singleStop ? ` · ${miles(match.dropoff_miles)}` : ""}</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="match-metric-row">
          <div className="match-metric">
            <span className="eyebrow">ETA</span>
            <span className="match-metric-value">{Math.round(match.eta_minutes)}<span className="text-sm font-semibold text-ink-3"> min</span></span>
          </div>
          <div className="match-metric">
            <span className="eyebrow">Food deadline</span>
            <span className="match-metric-value">{foodDeadline}<span className="text-sm font-semibold text-ink-3"> min</span></span>
          </div>
          <div className={`match-metric ${marginClass(safetyMargin)}`}>
            <span className="eyebrow">Safety margin</span>
            <span className="match-metric-value">{safetyMargin}<span className="text-sm font-semibold text-ink-3"> min</span></span>
          </div>
        </div>
      </div>
      {showMap && <FlowMap {...matchMapProps(match, rescue)} height={320} />}
      <WhyThisMatch candidates={match.top_candidates} reasons={match.reasons} />
    </section>
  );
}
