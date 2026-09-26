"use client";
// React Leaflet map. Loaded through components/Map.tsx with ssr: false.
// Tiles: Mapbox dark style when NEXT_PUBLIC_MAPBOX_TOKEN is set, otherwise Esri's free,
// keyless dark gray canvas basemap (CARTO's dark basemaps now require an API key).
import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { CircleMarker, MapContainer, Marker, Polygon, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import { iconMarkup, type IconName } from "./Icon";
import type { CensusArea } from "@/lib/types";

export type DriverState = "AVAILABLE" | "EN_ROUTE" | "ON_DELIVERY" | "OFFLINE";

export interface MapPoint {
  id: string; lat: number; lng: number; label: string; detail?: string;
  status?: DriverState; isNew?: boolean;
}
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
  /** Census tracts for the community-need choropleth (components/CommunityNeedLayer). */
  communityNeed?: CensusArea[];
  /** Uncontrolled by default (off, with its own toggle button); pass to control it externally. */
  showCommunityNeed?: boolean;
  onToggleCommunityNeed?: (show: boolean) => void;
  onSelectArea?: (area: CensusArea) => void;
}

const COLORS = {
  restaurant: "var(--m-restaurant)",
  org: "var(--m-org)",
  prospect: "var(--m-restaurant)",
  route: "var(--cyan)",
  muted: "var(--m-offline)",
};
const DRIVER_COLOR: Record<DriverState, string> = {
  AVAILABLE: "var(--m-driver)",
  EN_ROUTE: "var(--m-driver-active)",
  ON_DELIVERY: "var(--m-driver-active)",
  OFFLINE: "var(--m-offline)",
};
const MIAMI: [number, number] = [25.7574, -80.3733];
const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

function numberIcon(n: string) {
  return L.divIcon({ className: "", html: `<div class="map-num">${n}</div>`, iconSize: [22, 22], iconAnchor: [11, 11] });
}

// Round icon badge used for restaurants, organizations and drivers: a light disc (the icons have
// dark outlines) ringed in the marker type's color. `pulse` adds a live radar ring (currentColor),
// `newPulse` briefly flashes on creation (a fresh rescue), `offline` dims it.
export function badgeIcon(icon: IconName, color: string, opts: { size?: number; pulse?: boolean; offline?: boolean; selected?: boolean; newPulse?: boolean } = {}) {
  const { size = 32, pulse, offline, selected, newPulse } = opts;
  const classes = ["map-marker", pulse && "map-marker-pulse", offline && "is-offline", selected && "is-selected", newPulse && "marker-pulse-new"]
    .filter(Boolean).join(" ");
  return L.divIcon({
    className: "",
    html: `<div class="${classes}" style="border-color:${color};color:${color}">${iconMarkup(icon, Math.round(size * 0.68))}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
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
  const state = point.status ?? "EN_ROUTE";
  return (
    <Marker position={pos} icon={badgeIcon("car", DRIVER_COLOR[state], { size: 32, pulse: state !== "OFFLINE", offline: state === "OFFLINE" })}
      zIndexOffset={800}>
      <Tooltip direction="top" offset={[0, -16]}>
        <strong>{point.label}</strong>
        <div>{STATE_LABEL[state]}{point.detail ? ` · ${point.detail}` : ""}</div>
      </Tooltip>
    </Marker>
  );
}

const STATE_LABEL: Record<DriverState, string> = {
  AVAILABLE: "Available", EN_ROUTE: "En route", ON_DELIVERY: "On delivery", OFFLINE: "Offline",
};

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
          <Marker key={m.id} position={pointAlong(m.path, f)} icon={badgeIcon("car", DRIVER_COLOR.ON_DELIVERY, { size: 30, pulse: true })} zIndexOffset={800}>
            <Tooltip direction="top" offset={[0, -14]}>{m.name}</Tooltip>
          </Marker>
        );
      })}
    </>
  );
}

// Two layers on the same geometry: a soft glowing base so the route stays visible, plus a
// dashed overlay whose dash offset animates, reading as small particles moving toward the drop off.
function RouteLine({ route }: { route: MapRoute }) {
  if (route.muted) {
    return (
      <Polyline positions={route.geometry}
        pathOptions={{ color: COLORS.muted, weight: 3.5, opacity: 0.6, dashArray: "5 9", className: "route-muted" }} />
    );
  }
  return (
    <>
      <Polyline positions={route.geometry} pathOptions={{ color: COLORS.route, weight: 5, opacity: 0.35, className: "route-glow" }} />
      <Polyline positions={route.geometry}
        pathOptions={{ color: "#a5f3fc", weight: 2.5, opacity: 0.95, dashArray: "1 13", className: "route-particles" }} />
    </>
  );
}

// A subtle geographic overlay, not a heatmap: opacity (not an alarming red-to-green hue)
// scales with the Census-measured poverty rate, on the app's own blue/cyan palette, so it
// reads as "the network's supporting intelligence" rather than "a map of poor neighborhoods".
const NEED_FILL = { low: "#1e3a5f", moderate: "var(--accent)", high: "#0891b2", very_high: "var(--cyan)" };

function ringToLatLng(ring: number[][]): [number, number][] {
  return ring.map(([lng, lat]) => [lat, lng]);
}

function CommunityNeedLayer({ areas, onSelectArea }: { areas: CensusArea[]; onSelectArea?: (a: CensusArea) => void }) {
  return (
    <>
      {areas.map((a) => {
        const positions = a.geometry.type === "Polygon"
          ? (a.geometry.coordinates as number[][][]).map(ringToLatLng)
          : (a.geometry.coordinates as number[][][][]).map((poly) => poly.map(ringToLatLng));
        return (
          <Polygon key={a.geoid} positions={positions}
            pathOptions={{
              color: NEED_FILL[a.bucket], weight: 1, opacity: 0.25,
              fillColor: NEED_FILL[a.bucket], fillOpacity: 0.06 + a.community_need_score * 0.22,
            }}
            eventHandlers={onSelectArea ? { click: () => onSelectArea(a) } : undefined}>
            <Tooltip direction="top" sticky>
              <strong>{a.bucket_label} community need</strong>
              <div>{a.poverty_rate.toFixed(1)}% below the poverty line (Census tract estimate)</div>
            </Tooltip>
          </Polygon>
        );
      })}
    </>
  );
}

// Mapbox dark style when a token is configured, otherwise Esri's keyless dark gray canvas.
export function BaseTiles() {
  return MAPBOX_TOKEN ? (
    <TileLayer
      url={`https://api.mapbox.com/styles/v1/mapbox/dark-v11/tiles/512/{z}/{x}/{y}@2x?access_token=${MAPBOX_TOKEN}`}
      tileSize={512}
      zoomOffset={-1}
      attribution='&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    />
  ) : (
    <TileLayer
      url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
      attribution="&copy; Esri &amp; HERE, Garmin, OpenStreetMap contributors, and the GIS user community"
    />
  );
}

export default function MapView({
  restaurants = [], drivers = [], organizations = [], prospects = [], reference = null, selectedId = null, onSelect,
  routes = [], movers = [], chips = [], height = 380, fitKey,
  communityNeed = [], showCommunityNeed, onToggleCommunityNeed, onSelectArea,
}: MapViewProps) {
  const [internalShow, setInternalShow] = useState(false);
  const show = showCommunityNeed ?? internalShow;
  const toggle = () => (onToggleCommunityNeed ? onToggleCommunityNeed(!show) : setInternalShow((s) => !s));
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
        <BaseTiles />
        <FitBounds points={allPoints} fitKey={key} />

        {show && communityNeed.length > 0 && <CommunityNeedLayer areas={communityNeed} onSelectArea={onSelectArea} />}

        {routes.map((r) => <RouteLine key={r.id} route={r} />)}
        {routes.flatMap((r) =>
          (r.stops ?? []).map((s, i) => (
            <Marker key={`${r.id}-stop-${i}`} position={[s.lat, s.lng]} icon={numberIcon(String(i + 1))}
              zIndexOffset={1000} keyboard={false} title={`Stop ${i + 1}: ${s.label}`} />
          )),
        )}

        {restaurants.map((p) => (
          <Marker key={p.id} position={[p.lat, p.lng]} icon={badgeIcon("restaurant", COLORS.restaurant, { newPulse: p.isNew })} zIndexOffset={600}>
            <Tooltip direction="top" offset={[0, -16]}><strong>{p.label}</strong>{p.detail ? <div>{p.detail}</div> : null}</Tooltip>
          </Marker>
        ))}
        {organizations.map((p) => (
          <Marker key={p.id} position={[p.lat, p.lng]} icon={badgeIcon("community-org", COLORS.org)} zIndexOffset={600}>
            <Tooltip direction="top" offset={[0, -16]}><strong>{p.label}</strong>{p.detail ? <div>{p.detail}</div> : null}</Tooltip>
          </Marker>
        ))}
        {prospects.map((p) => (
          <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={p.id === selectedId ? 11 : 8}
            eventHandlers={onSelect ? { click: () => onSelect(p.id) } : undefined}
            pathOptions={{ color: COLORS.prospect, weight: p.id === selectedId ? 4 : 3, fillColor: "var(--panel)", fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]}><strong>{p.label}</strong>{p.detail ? <div>{p.detail}</div> : null}</Tooltip>
          </CircleMarker>
        ))}
        {reference && (
          <CircleMarker center={[reference.lat, reference.lng]} radius={7} pathOptions={{ color: "var(--ink)", weight: 2, fillColor: "var(--panel)", fillOpacity: 1 }}>
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
      {communityNeed.length > 0 && (
        <button type="button" onClick={toggle}
          className={`absolute right-2 z-[1000] chip ${show ? "chip-accent" : ""}`} style={{ top: chips.length > 0 ? 40 : 8 }}
          aria-pressed={show}>
          Community Need: {show ? "ON" : "OFF"}
        </button>
      )}
      <div className="absolute bottom-2 left-2 z-[1000] flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-line bg-panel/85 px-2.5 py-1 text-xs text-ink-2 backdrop-blur"
        title="Community need: Census-tract poverty rate, low to very high. FoodFlow visualization buckets, not official Census categories. Source: 2024 ACS 5-Year Estimates.">
        {restaurants.length > 0 && <Legend color={COLORS.restaurant} label="Restaurant" />}
        {prospects.length > 0 && <Legend color={COLORS.prospect} label="Prospect" ring />}
        {(drivers.length > 0 || movers.length > 0) && <Legend color={DRIVER_COLOR.EN_ROUTE} label="Driver" />}
        {organizations.length > 0 && <Legend color={COLORS.org} label="Organization" />}
        {show && communityNeed.length > 0 && (
          <>
            <span className="h-3 w-px bg-line" aria-hidden />
            <Legend color={NEED_FILL.low} label="Low" />
            <Legend color={NEED_FILL.moderate} label="Mod." />
            <Legend color={NEED_FILL.high} label="High" />
            <Legend color={NEED_FILL.very_high} label="V.High need" />
          </>
        )}
      </div>
    </div>
  );
}

function Legend({ color, label, ring = false }: { color: string; label: string; ring?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <i aria-hidden className="inline-block h-3 w-3 rounded-full" style={ring ? { border: `3px solid ${color}`, background: "var(--panel)" } : { background: color }} />
      {label}
    </span>
  );
}
