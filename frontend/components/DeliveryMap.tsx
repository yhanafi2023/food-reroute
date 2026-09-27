"use client";
import { useEffect, useState } from "react";
import FlowMap from "./FlowMap";
import { roadRoute } from "@/lib/osrm";
import { useCommunityNeedAreas } from "@/lib/useCommunityNeed";
import type { Rescue, Trip } from "@/lib/types";

// The real backend never returns a routed polyline (app/dispatch.py stores only trip-cost
// metadata, not geometry) and never returns a driver's live position to a restaurant or
// organization view (app/views.py: "Volunteers' ... home locations are never returned to
// anyone but admins"). This draws the actual road route (OSRM) between the fixed pickup and
// drop-off points; it does not show a moving carrier dot outside the admin network view.
function useRoadRoute(waypoints: [number, number][]): [number, number][] {
  const straight = waypoints;
  const [line, setLine] = useState<[number, number][]>(straight);
  const key = waypoints.map((p) => p.join(",")).join("|");
  useEffect(() => {
    let cancelled = false;
    setLine(straight);
    roadRoute(waypoints).then((real) => { if (real && !cancelled) setLine(real); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return line;
}

function tripWaypoints(rescue: Rescue, trip: Trip): [number, number][] {
  const r = rescue.restaurant;
  return [[r.lat, r.lng], ...trip.stops.map((s) => [s.organization.lat, s.organization.lng] as [number, number])];
}

// A scheduled rescue's map always shows the community-need layer: the regions this
// delivery is moving food through, and how they compare, are exactly the context that
// makes the match legible -- not something to hide behind a toggle here.
export default function DeliveryMap({ rescue, trip, height = 340 }: { rescue: Rescue; trip: Trip; height?: number }) {
  const areas = useCommunityNeedAreas();
  const [showNeed, setShowNeed] = useState(true);
  const waypoints = tripWaypoints(rescue, trip);
  const geometry = useRoadRoute(waypoints);
  const r = rescue.restaurant;

  return (
    <FlowMap
      restaurants={[{ id: `r${r.id}`, lat: r.lat, lng: r.lng, label: r.name, detail: "Pickup" }]}
      organizations={trip.stops.map((s) => ({
        id: `o${s.organization.id}`, lat: s.organization.lat, lng: s.organization.lng, label: s.organization.name,
        detail: `${s.allocated_meals} meals · ${s.status}`,
      }))}
      routes={[{
        id: `trip${trip.id}`, geometry,
        stops: trip.stops.map((s) => ({ lat: s.organization.lat, lng: s.organization.lng, label: s.organization.name })),
        muted: ["delivered", "received", "cancelled", "rejected", "expired"].includes(trip.status),
      }]}
      communityNeed={areas} showCommunityNeed={showNeed} onToggleCommunityNeed={setShowNeed}
      height={height} fitKey={`trip${trip.id}-${trip.status}`}
    />
  );
}

// No carrier yet (still searching, or none is currently feasible): still show the
// restaurant on the community-need layer, so a rescue never posts without a map.
export function RescueAreaMap({ rescue, height = 440 }: { rescue: Rescue; height?: number }) {
  const areas = useCommunityNeedAreas();
  const [showNeed, setShowNeed] = useState(true);
  const r = rescue.restaurant;
  return (
    <FlowMap
      restaurants={[{ id: `r${r.id}`, lat: r.lat, lng: r.lng, label: r.name, detail: "Searching for a carrier and an organization", isNew: true }]}
      communityNeed={areas} showCommunityNeed={showNeed} onToggleCommunityNeed={setShowNeed}
      height={height} fitKey={`rescue${rescue.id}-searching`}
    />
  );
}
