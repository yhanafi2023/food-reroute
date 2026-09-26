"use client";
// The landing page's hero map: an illustration built from fixed example data, not live
// network state. Hot zones mark the kind of high-need neighborhoods FoodFlow routes toward;
// cars loop along example pickup -> drop-off routes. Loaded through LandingMap with ssr: false.
import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, MapContainer, Marker, Polyline, Tooltip, useMap } from "react-leaflet";
import { iconMarkup } from "./Icon";
import { BaseTiles, badgeIcon, pointAlong } from "./MapView";
import { roadRoute } from "@/lib/osrm";

type LatLng = [number, number];

// Approximate centers of Miami neighborhoods with high Census-measured poverty rates.
// Radii are illustrative, not tract boundaries.
const HOTZONES: { id: string; name: string; center: LatLng; radius: number; level: "High" | "Very high" }[] = [
  { id: "liberty-city", name: "Liberty City", center: [25.8335, -80.2300], radius: 1500, level: "Very high" },
  { id: "little-haiti", name: "Little Haiti", center: [25.8300, -80.1965], radius: 1050, level: "High" },
  { id: "allapattah", name: "Allapattah", center: [25.8140, -80.2250], radius: 1150, level: "High" },
  { id: "overtown", name: "Overtown", center: [25.7865, -80.2025], radius: 900, level: "Very high" },
  { id: "little-havana", name: "Little Havana", center: [25.7690, -80.2240], radius: 1250, level: "High" },
];

const RESTAURANTS = [
  { id: "abc", name: "ABC Restaurant", detail: "50 meals · pickup before 10 PM", at: [25.7640, -80.1925] as LatLng },
  { id: "wyn", name: "Wynwood Kitchen", detail: "24 meals · pickup before 9 PM", at: [25.8010, -80.1990] as LatLng },
  { id: "gab", name: "Gables Bistro", detail: "36 meals · pickup before 11 PM", at: [25.7500, -80.2590] as LatLng },
];

const ORGS = [
  { id: "hope", name: "Hope Shelter", detail: "Receiving 20 meals", at: [25.7880, -80.2045] as LatLng },
  { id: "cfb", name: "Community Food Bank", detail: "Receiving 30 meals", at: [25.8345, -80.2265] as LatLng },
  { id: "pantry", name: "Northside School Pantry", detail: "Receiving 24 meals", at: [25.8285, -80.1940] as LatLng },
  { id: "senior", name: "Riverside Senior Center", detail: "Receiving 16 meals", at: [25.7705, -80.2200] as LatLng },
  { id: "family", name: "Family Resource Center", detail: "Receiving 20 meals", at: [25.8130, -80.2280] as LatLng },
];

const at = (list: { id: string; at: LatLng }[], id: string) => list.find((x) => x.id === id)!.at;

// Each route: one pickup, then its drop offs in order. `lapMs` is one full drive.
const ROUTES = [
  { id: "a", driver: "Marcus", waypoints: [at(RESTAURANTS, "abc"), at(ORGS, "hope"), at(ORGS, "cfb")], lapMs: 14000, offset: 0 },
  { id: "b", driver: "Ana", waypoints: [at(RESTAURANTS, "wyn"), at(ORGS, "pantry")], lapMs: 9000, offset: 3500 },
  { id: "c", driver: "Luis", waypoints: [at(RESTAURANTS, "gab"), at(ORGS, "senior"), at(ORGS, "family")], lapMs: 15000, offset: 7000 },
];

const PAUSE_MS = 1400;

// Straight lines first; swapped for real road geometry (OSRM) when it arrives.
function useRoadGeometry() {
  const [lines, setLines] = useState<Record<string, LatLng[]>>(() =>
    Object.fromEntries(ROUTES.map((r) => [r.id, r.waypoints])));
  useEffect(() => {
    let cancelled = false;
    ROUTES.forEach((r) => {
      roadRoute(r.waypoints).then((real) => {
        if (real && !cancelled) setLines((prev) => ({ ...prev, [r.id]: real }));
      });
    });
    return () => { cancelled = true; };
  }, []);
  return lines;
}

function Fit({ points }: { points: LatLng[] }) {
  const map = useMap();
  useEffect(() => {
    const bounds = L.latLngBounds(points);
    HOTZONES.forEach((z) => bounds.extend(L.latLng(z.center).toBounds(z.radius)));
    const fit = () => {
      const wide = map.getContainer().clientWidth >= 1024;
      // Clear the chips (top), the legend (bottom) and, on desktop, the example-match card (right).
      map.fitBounds(bounds, {
        paddingTopLeft: [32, 56], paddingBottomRight: wide ? [380, 48] : [32, 48],
      });
    };
    fit();
    map.on("resize", fit);
    return () => { map.off("resize", fit); };
  }, [map, points]);
  return null;
}

// Heading in degrees clockwise from north, for rotating the top-down car.
function bearing(a: LatLng, b: LatLng) {
  const dy = b[0] - a[0];
  const dx = (b[1] - a[1]) * Math.cos((a[0] * Math.PI) / 180);
  return (Math.atan2(dx, dy) * 180) / Math.PI;
}

// Cars are imperative Leaflet markers moved every frame, so the loop never re-renders React.
function Cars({ lines }: { lines: Record<string, LatLng[]> }) {
  const map = useMap();
  const linesRef = useRef(lines);
  useEffect(() => { linesRef.current = lines; }, [lines]);

  useEffect(() => {
    const cars = ROUTES.map((r) => {
      const marker = L.marker(r.waypoints[0], {
        icon: L.divIcon({ className: "", html: `<div class="map-car">${iconMarkup("car-top", 30)}</div>`, iconSize: [30, 30], iconAnchor: [15, 15] }),
        interactive: false, keyboard: false, zIndexOffset: 900,
      }).addTo(map);
      return { route: r, marker };
    });
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      for (const { route, marker } of cars) {
        const path = linesRef.current[route.id];
        const cycle = route.lapMs + PAUSE_MS;
        const f = reduced ? 0.5 : Math.min(((now - t0 + route.offset) % cycle) / route.lapMs, 1);
        const p = pointAlong(path, f);
        const ahead = pointAlong(path, Math.min(f + 0.01, 1));
        marker.setLatLng(p);
        const el = marker.getElement()?.firstElementChild as HTMLElement | null;
        if (el) {
          if (f < 0.995) el.style.transform = `rotate(${bearing(p, ahead)}deg)`;
          el.style.opacity = f >= 1 ? "0" : "1";
        }
      }
      if (!reduced) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      cars.forEach((c) => c.marker.remove());
    };
  }, [map]);
  return null;
}

export default function LandingMapView() {
  const lines = useRoadGeometry();
  const points = useMemo<LatLng[]>(() => [...RESTAURANTS.map((r) => r.at), ...ORGS.map((o) => o.at)], []);

  return (
    <div className="map-shell h-full">
      {/* Soft radial fill shared by every hot zone circle (referenced as url(#ff-hotzone)). */}
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
        <defs>
          <radialGradient id="ff-hotzone">
            <stop offset="0%" stopColor="#ef4444" stopOpacity="0.75" />
            <stop offset="40%" stopColor="#f97316" stopOpacity="0.42" />
            <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
          </radialGradient>
        </defs>
      </svg>
      <MapContainer center={[25.795, -80.215]} zoom={13} style={{ height: "100%", width: "100%" }}
        zoomSnap={0.25} scrollWheelZoom={false} dragging={false} doubleClickZoom={false} touchZoom={false} boxZoom={false}
        keyboard={false} zoomControl={false}>
        <BaseTiles />
        <Fit points={points} />

        {HOTZONES.map((z, i) => (
          <Circle key={z.id} center={z.center} radius={z.radius}
            pathOptions={{ stroke: false, fillColor: "url(#ff-hotzone)", fillOpacity: 1, className: `hotzone hotzone-${i % 3}` }}>
            <Tooltip direction="top" sticky>
              <strong>{z.name}</strong>
              <div>{z.level} community need (example)</div>
            </Tooltip>
          </Circle>
        ))}
        {HOTZONES.map((z, i) => (
          <Circle key={`${z.id}-ring`} center={z.center} radius={z.radius * 0.55} interactive={false}
            pathOptions={{ color: "#fb923c", weight: 1.5, opacity: 0.9, fill: false, dashArray: "3 6", className: `hotzone-ring hotzone-${i % 3}` }} />
        ))}

        {ROUTES.map((r) => (
          <RouteLayers key={r.id} line={lines[r.id]} />
        ))}

        {RESTAURANTS.map((r) => (
          <Marker key={r.id} position={r.at} icon={badgeIcon("restaurant", "var(--m-restaurant)", { size: 36 })} zIndexOffset={600}>
            <Tooltip direction="top" offset={[0, -18]}><strong>{r.name}</strong><div>{r.detail}</div></Tooltip>
          </Marker>
        ))}
        {ORGS.map((o) => (
          <Marker key={o.id} position={o.at} icon={badgeIcon("community-org", "var(--m-org)", { size: 34, pulse: true })} zIndexOffset={600}>
            <Tooltip direction="top" offset={[0, -18]}><strong>{o.name}</strong><div>{o.detail}</div></Tooltip>
          </Marker>
        ))}
        <Cars lines={lines} />
      </MapContainer>

      <div className="absolute left-3 top-3 z-[1000] flex flex-wrap gap-2">
        <span className="chip chip-accent"><i aria-hidden className="landing-live-dot" /> 3 drivers en route</span>
        <span className="chip">Example routes · demo data</span>
      </div>
      <div className="absolute bottom-2 left-2 z-[1000] flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-line bg-panel/85 px-2.5 py-1 text-xs text-ink-2 backdrop-blur">
        <span className="inline-flex items-center gap-1"><i aria-hidden className="inline-block h-3 w-3 rounded-full" style={{ background: "var(--m-restaurant)" }} />Restaurant</span>
        <span className="inline-flex items-center gap-1"><i aria-hidden className="inline-block h-3 w-3 rounded-full" style={{ background: "var(--m-driver)" }} />Driver</span>
        <span className="inline-flex items-center gap-1"><i aria-hidden className="inline-block h-3 w-3 rounded-full" style={{ background: "var(--m-org)" }} />Organization</span>
        <span className="inline-flex items-center gap-1"><i aria-hidden className="inline-block h-3 w-3 rounded-full" style={{ background: "radial-gradient(#ef4444, #f97316 55%, transparent)" }} />High need area</span>
      </div>
    </div>
  );
}

// A dim base, a glow that draws itself in once, and flowing particles toward the drop offs.
function RouteLayers({ line }: { line: LatLng[] }) {
  return (
    <>
      <Polyline positions={line} interactive={false} pathOptions={{ color: "#1e3a5f", weight: 6, opacity: 0.9 }} />
      <Polyline positions={line} interactive={false} pathOptions={{ color: "var(--cyan)", weight: 4, opacity: 0.45, className: "route-glow route-draw" }} />
      <Polyline positions={line} interactive={false}
        pathOptions={{ color: "#a5f3fc", weight: 2.5, opacity: 0.95, dashArray: "1 13", className: "route-particles" }} />
    </>
  );
}
