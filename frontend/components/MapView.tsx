"use client";
// React Leaflet map. Loaded through components/Map.tsx with ssr: false.
// Tiles: Mapbox streets when NEXT_PUBLIC_MAPBOX_TOKEN is set, otherwise OpenStreetMap.
import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";

export interface MapPoint { id: string; lat: number; lng: number; label: string; detail?: string }
export interface MapRoute { id: string; geometry: [number, number][]; stops?: { lat: number; lng: number; label: string }[]; muted?: boolean }
export interface Mover { id: string; name: string; path: [number, number][]; startedAt: number; durationMs: number }

export interface MapViewProps {
  restaurants?: MapPoint[];
  drivers?: MapPoint[];
  organizations?: MapPoint[];
  prospects?: MapPoint[];
  reference?: MapPoint | null;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  routes?: MapRoute[];
  movers?: Mover[];
  chips?: string[];
  height?: number;
  fitKey?: string;
}

const COLORS = { restaurant: "#e0701c", driver: "#1456d9", org: "#14734a", route: "#1456d9", muted: "#8aa2c4" };
const MIAMI: [number, number] = [25.7574, -80.3733];
const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

function numberIcon(n: string) {
  return L.divIcon({ className: "", html: `<div class="map-num">${n}</div>`, iconSize: [22, 22], iconAnchor: [11, 11] });
}

// Position `fraction` (0..1) of the way along a polyline, by distance.
export function pointAlong(path: [number, number][], fraction: number): [number, number] {
  if (path.length === 0) return MIAMI;
  if (path.length === 1 || fraction <= 0) return path[0];
  if (fraction >= 1) return path[path.length - 1];
  const seg: number[] = [];
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    const d = Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
    seg.push(d);
    total += d;
  }
  let target = total * fraction;
  for (let i = 0; i < seg.length; i++) {
    if (target <= seg[i] || i === seg.length - 1) {
      const f = seg[i] === 0 ? 0 : target / seg[i];
      return [path[i][0] + (path[i + 1][0] - path[i][0]) * f, path[i][1] + (path[i + 1][1] - path[i][1]) * f];
    }
    target -= seg[i];
  }
  return path[path.length - 1];
}

function FitBounds({ points, fitKey }: { points: [number, number][]; fitKey: string }) {
  const map = useMap();
  const last = useRef<string>("");
  useEffect(() => {
    if (!points.length || last.current === fitKey) return;
    last.current = fitKey;
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 15 });
  }, [map, points, fitKey]);
  return null;
}

// A driver marker that glides to its new position instead of jumping.
function GlidingDriver({ point }: { point: MapPoint }) {
  const [pos, setPos] = useState<[number, number]>([point.lat, point.lng]);
  const from = useRef<[number, number]>([point.lat, point.lng]);
  useEffect(() => {
    const start = from.current;
    const end: [number, number] = [point.lat, point.lng];
    if (start[0] === end[0] && start[1] === end[1]) return;
    let raf = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const f = Math.min((now - t0) / 1200, 1);
      const eased = 1 - Math.pow(1 - f, 3);
      const p: [number, number] = [start[0] + (end[0] - start[0]) * eased, start[1] + (end[1] - start[1]) * eased];
      from.current = p;
      setPos(p);
      if (f < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [point.lat, point.lng]);
  return (
    <CircleMarker center={pos} radius={9} pathOptions={{ color: "#fff", weight: 3, fillColor: COLORS.driver, fillOpacity: 1 }}>
      <Tooltip direction="top" offset={[0, -8]}>
        <strong>{point.label}</strong>
        {point.detail ? <div>{point.detail}</div> : null}
      </Tooltip>
    </CircleMarker>
  );
}

// Drivers animating along routes (Simulate Tonight). Driven by requestAnimationFrame and elapsed time.
function Movers({ movers }: { movers: Mover[] }) {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!movers.length) return;
    let raf = 0;
    const tick = (t: number) => {
      setNow(t);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [movers.length]);
  return (
    <>
      {movers.map((m) => {
        const f = Math.max(0, Math.min((now - m.startedAt) / Math.max(m.durationMs, 1), 1));
        return (
          <CircleMarker key={m.id} center={pointAlong(m.path, f)} radius={6}
            pathOptions={{ color: "#fff", weight: 3, fillColor: COLORS.driver, fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]}>{m.name}</Tooltip>
          </CircleMarker>
        );
      })}
    </>
  );
}

export default function MapView({
  restaurants = [], drivers = [], organizations = [], prospects = [], reference = null, selectedId = null, onSelect,
  routes = [], movers = [], chips = [], height = 380, fitKey,
}: MapViewProps) {
  const allPoints = useMemo<[number, number][]>(
    () => [
      ...restaurants.map((p) => [p.lat, p.lng] as [number, number]),
      ...drivers.map((p) => [p.lat, p.lng] as [number, number]),
      ...organizations.map((p) => [p.lat, p.lng] as [number, number]),
      ...prospects.map((p) => [p.lat, p.lng] as [number, number]),
      ...routes.flatMap((r) => r.geometry),
    ],
    [restaurants, drivers, organizations, prospects, routes],
  );
  const key = fitKey ?? [...restaurants, ...drivers, ...organizations, ...prospects].map((p) => p.id).concat(routes.map((r) => r.id)).join("|");

  return (
    <div className="map-shell" style={{ height }}>
      <MapContainer center={MIAMI} zoom={13} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
        {MAPBOX_TOKEN ? (
          <TileLayer
            url={`https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/512/{z}/{x}/{y}@2x?access_token=${MAPBOX_TOKEN}`}
            tileSize={512}
            zoomOffset={-1}
            attribution='&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          />
        ) : (
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          />
        )}
        <FitBounds points={allPoints} fitKey={key} />

        {routes.map((r) => (
          <Polyline key={r.id} positions={r.geometry}
            pathOptions={{ color: r.muted ? COLORS.muted : COLORS.route, weight: r.muted ? 4 : 6, opacity: 0.9, dashArray: r.muted ? "6 8" : undefined }} />
        ))}
        {routes.flatMap((r) =>
          (r.stops ?? []).map((s, i) => (
            <Marker key={`${r.id}-stop-${i}`} position={[s.lat, s.lng]} icon={numberIcon(String(i + 1))}
              zIndexOffset={1000} keyboard={false} title={`Stop ${i + 1}: ${s.label}`} />
          )),
        )}

        {restaurants.map((p) => (
          <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={9}
            pathOptions={{ color: "#fff", weight: 2, fillColor: COLORS.restaurant, fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]}><strong>{p.label}</strong>{p.detail ? <div>{p.detail}</div> : null}</Tooltip>
          </CircleMarker>
        ))}
        {organizations.map((p) => (
          <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={9}
            pathOptions={{ color: "#fff", weight: 2, fillColor: COLORS.org, fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]}><strong>{p.label}</strong>{p.detail ? <div>{p.detail}</div> : null}</Tooltip>
          </CircleMarker>
        ))}
        {prospects.map((p) => (
          <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={p.id === selectedId ? 11 : 8}
            eventHandlers={onSelect ? { click: () => onSelect(p.id) } : undefined}
            pathOptions={{ color: COLORS.restaurant, weight: p.id === selectedId ? 4 : 3, fillColor: "#fff", fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]}><strong>{p.label}</strong>{p.detail ? <div>{p.detail}</div> : null}</Tooltip>
          </CircleMarker>
        ))}
        {reference && (
          <CircleMarker center={[reference.lat, reference.lng]} radius={7} pathOptions={{ color: "#fff", weight: 2, fillColor: "#0e1a2b", fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]} permanent><strong>{reference.label}</strong></Tooltip>
          </CircleMarker>
        )}
        {drivers.map((p) => <GlidingDriver key={p.id} point={p} />)}
        <Movers movers={movers} />
      </MapContainer>

      {chips.length > 0 && (
        <div className="absolute right-2 top-2 z-[1000] flex flex-wrap justify-end gap-1" aria-live="polite">
          {chips.map((c) => <span key={c} className="chip chip-accent">{c}</span>)}
        </div>
      )}
      <div className="absolute bottom-2 left-2 z-[1000] flex flex-wrap gap-2 rounded-md bg-white/90 px-2 py-1 text-xs font-semibold text-ink-2">
        {restaurants.length > 0 && <Legend color={COLORS.restaurant} label="Restaurant (demo partner)" />}
        {prospects.length > 0 && <Legend color={COLORS.restaurant} label="Researched prospect, not a partner" ring />}
        {(drivers.length > 0 || movers.length > 0) && <Legend color={COLORS.driver} label="Driver" />}
        {organizations.length > 0 && <Legend color={COLORS.org} label="Organization" />}
      </div>
    </div>
  );
}

function Legend({ color, label, ring = false }: { color: string; label: string; ring?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <i aria-hidden className="inline-block h-3 w-3 rounded-full" style={ring ? { border: `3px solid ${color}`, background: "#fff" } : { background: color }} />
      {label}
    </span>
  );
}
