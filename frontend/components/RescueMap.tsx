"use client";
// SSR-safe wrapper: Leaflet touches `window`, so the map loads only in the browser.
// Builds map points from the current API shapes. Only data the backend already returned to this
// viewer is drawn (orgs only appear for rescues this role may see). The backend does not expose
// carrier positions yet, so no carrier markers are drawn from guesses. Route lines become OSRM road
// routes when they load (a073982).
import dynamic from "next/dynamic";
import type { Rescue } from "@/lib/types";
import { activeTrip } from "./RescueCard";
import type { MapPoint, MapRoute, RescueMapViewProps } from "./RescueMapView";

// Any map (prospects, rescues): the Leaflet view without server rendering.
export const MapCanvas = dynamic(() => import("./RescueMapView"), {
  ssr: false,
  loading: () => <div className="skeleton" style={{ height: 380 }} role="status" aria-label="Loading map" />,
});

const ROUTE_NOTE = "Straight lines between stops until the road route loads";

export function mapPropsFor(rescues: Rescue[]): RescueMapViewProps {
  const restaurants = new Map<string, MapPoint>();
  const organizations = new Map<string, MapPoint>();
  const routes: MapRoute[] = [];
  for (const r of rescues) {
    const key = `r${r.restaurant.id}`;
    const prev = restaurants.get(key);
    restaurants.set(key, {
      id: key,
      lat: r.restaurant.lat,
      lng: r.restaurant.lng,
      label: r.restaurant.name,
      detail: prev ? `${prev.detail}; #${r.id}` : `Donation #${r.id}, ${r.est_meals} meals`,
      isNew: r.status === "posted",
    });
    const trip = activeTrip(r);
    if (!trip || ["cancelled", "reassigned", "expired"].includes(trip.status)) continue;
    const stops = [...trip.stops].sort((a, b) => a.seq - b.seq);
    for (const s of stops) {
      organizations.set(`o${s.organization.id}`, {
        id: `o${s.organization.id}`,
        lat: s.organization.lat,
        lng: s.organization.lng,
        label: s.organization.name,
        detail: `${s.allocated_meals} meals from ${r.restaurant.name}`,
      });
    }
    routes.push({
      id: `t${trip.id}`,
      geometry: [[r.restaurant.lat, r.restaurant.lng], ...stops.map((s) => [s.organization.lat, s.organization.lng] as [number, number])],
      stops: stops.map((s) => ({ lat: s.organization.lat, lng: s.organization.lng, label: s.organization.name })),
      muted: ["delivered", "received"].includes(trip.status),
    });
  }
  return { restaurants: [...restaurants.values()], organizations: [...organizations.values()], routes, routeNote: routes.length ? ROUTE_NOTE : undefined };
}

export default function RescueMap({ rescues, height = 380, communityNeed = false }: { rescues: Rescue[]; height?: number; communityNeed?: boolean }) {
  return <MapCanvas {...mapPropsFor(rescues)} height={height} communityNeed={communityNeed} fitKey={rescues.map((r) => r.id).join("|")} />;
}
