"use client";
// React Leaflet map, ported from MapView in 238b63d (dark basemap, emoji badge markers, glowing
// route with moving particles, numbered stops, gliding carrier markers, legend). Fed from the
// current API types through components/RescueMap.tsx, which loads this file with ssr: false.
// Tiles: Mapbox dark when NEXT_PUBLIC_MAPBOX_TOKEN is set, otherwise Esri's keyless dark gray canvas.
import L from "leaflet";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { CircleMarker, MapContainer, Marker, Polygon, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import { roadRoute } from "@/lib/osrm";
import { useCommunityNeedAreas } from "@/lib/useCommunityNeed";
import type { CensusArea } from "@/lib/types";

export type CarrierState = "AVAILABLE" | "EN_ROUTE" | "ON_DELIVERY" | "OFFLINE";

export interface MapPoint {
  id: string;
  lat: number;
  lng: number;
  label: string;
  detail?: string;
  status?: CarrierState;
  isNew?: boolean;
}
export interface MapRoute {
  id: string;
  geometry: [number, number][];
  stops?: { lat: number; lng: number; label: string }[];
  muted?: boolean;
}

export interface RescueMapViewProps {
  restaurants?: MapPoint[];
  organizations?: MapPoint[];
  carriers?: MapPoint[];
  prospects?: MapPoint[];
  reference?: MapPoint | null;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  routes?: MapRoute[];
  /** Replace straight route lines with OSRM road geometry when it loads (cached per session). */
  roadRoutes?: boolean;
  /** Offer the Census community-need layer (a073982) when GET /community-need/areas has data. */
  communityNeed?: boolean;
  height?: number;
  fitKey?: string;
  routeNote?: string;
}

const COLORS = { restaurant: "var(--m-restaurant)", org: "var(--m-org)", prospect: "var(--m-restaurant)", route: "var(--cyan)", muted: "var(--m-offline)" };
const CARRIER_COLOR: Record<CarrierState, string> = {
  AVAILABLE: "var(--m-driver)",
  EN_ROUTE: "var(--m-driver-active)",
  ON_DELIVERY: "var(--m-driver-active)",
  OFFLINE: "var(--m-offline)",
};
const STATE_LABEL: Record<CarrierState, string> = { AVAILABLE: "Available", EN_ROUTE: "En route", ON_DELIVERY: "On delivery", OFFLINE: "Offline" };
const FIU: [number, number] = [25.7574, -80.3733];
const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

// Basemap follows the theme: dark gray canvas by default (238b63d), light gray canvas in light theme.
function useLightTheme(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const obs = new MutationObserver(cb);
      obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      return () => obs.disconnect();
    },
    () => document.documentElement.dataset.theme === "light",
    () => false,
  );
}

function numberIcon(n: string) {
  return L.divIcon({ className: "", html: `<div class="map-num">${n}</div>`, iconSize: [22, 22], iconAnchor: [11, 11] });
}

// Round emoji badge. `pulse` adds a live radar ring, `newPulse` flashes on creation, `offline` dims it.
function emojiIcon(emoji: string, color: string, opts: { size?: number; pulse?: boolean; offline?: boolean; newPulse?: boolean } = {}) {
  const { size = 30, pulse, offline, newPulse } = opts;
  const classes = ["map-marker", pulse && "map-marker-pulse", offline && "is-offline", newPulse && "marker-pulse-new"].filter(Boolean).join(" ");
  return L.divIcon({
    className: "",
    html: `<div class="${classes}" style="background:${color};color:${color}">${emoji}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function FitBounds({ points, fitKey }: { points: [number, number][]; fitKey: string }) {
  const map = useMap();
  const last = useRef<string>("");
  useEffect(() => {
    if (!points.length || last.current === fitKey) return;
    last.current = fitKey;
    map.fitBounds(L.latLngBounds(points), { paddingTopLeft: [40, 80], paddingBottomRight: [40, 40], maxZoom: 15 });
  }, [map, points, fitKey]);
  return null;
}

// A carrier marker that glides to its new position instead of jumping.
function GlidingCarrier({ point }: { point: MapPoint }) {
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
    <Marker position={pos} icon={emojiIcon("🚗", CARRIER_COLOR[state], { size: 30, pulse: state !== "OFFLINE", offline: state === "OFFLINE" })} zIndexOffset={800}>
      <Tooltip direction="top" offset={[0, -16]}>
        <strong>{point.label}</strong>
        <div>
          {STATE_LABEL[state]}
          {point.detail ? ` · ${point.detail}` : ""}
        </div>
      </Tooltip>
    </Marker>
  );
}

// Two layers on the same geometry: a soft glowing base so the route stays visible, plus a dashed
// overlay whose dash offset animates, reading as particles moving toward the drop off.
function RouteLine({ route }: { route: MapRoute }) {
  if (route.muted) {
    return <Polyline positions={route.geometry} pathOptions={{ color: COLORS.muted, weight: 3.5, opacity: 0.6, dashArray: "5 9", className: "route-muted" }} />;
  }
  return (
    <>
      <Polyline positions={route.geometry} pathOptions={{ color: COLORS.route, weight: 5, opacity: 0.35, className: "route-glow" }} />
      <Polyline positions={route.geometry} pathOptions={{ color: "#a5f3fc", weight: 2.5, opacity: 0.95, dashArray: "1 13", className: "route-particles" }} />
    </>
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

// Road geometry for each route from OSRM, falling back to the straight line (a073982's DeliveryMap).
function useRoadGeometry(routes: MapRoute[], enabled: boolean): { routes: MapRoute[]; allRoad: boolean } {
  const [lines, setLines] = useState<Record<string, [number, number][]>>({});
  const key = routes.map((r) => `${r.id}:${r.geometry.map((p) => p.join(",")).join(";")}`).join("|");
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    routes.forEach((r) =>
      roadRoute(r.geometry).then((line) => {
        if (line && !cancelled) setLines((prev) => ({ ...prev, [r.id]: line }));
      }),
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);
  const merged = routes.map((r) => (enabled && lines[r.id] ? { ...r, geometry: lines[r.id] } : r));
  return { routes: merged, allRoad: enabled && routes.length > 0 && routes.every((r) => !!lines[r.id]) };
}

// Census-tract community need (a073982): opacity scales with the tract's poverty rate on the app's
// blue/cyan palette, so it reads as context, not an alarm. Only drawn when the backend serves areas.
const NEED_FILL = { low: "#1e3a5f", moderate: "var(--accent)", high: "#0891b2", very_high: "var(--cyan)" };

function ringToLatLng(ring: number[][]): [number, number][] {
  return ring.map(([lng, lat]) => [lat, lng]);
}

function CommunityNeedLayer({ areas }: { areas: CensusArea[] }) {
  return (
    <>
      {areas.map((a) => {
        const positions =
          a.geometry.type === "Polygon"
            ? (a.geometry.coordinates as number[][][]).map(ringToLatLng)
            : (a.geometry.coordinates as number[][][][]).map((poly) => poly.map(ringToLatLng));
        return (
          <Polygon
            key={a.geoid}
            positions={positions}
            pathOptions={{ color: NEED_FILL[a.bucket], weight: 1, opacity: 0.25, fillColor: NEED_FILL[a.bucket], fillOpacity: 0.06 + a.community_need_score * 0.22 }}
          >
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

export default function RescueMapView({
  restaurants = [],
  organizations = [],
  carriers = [],
  prospects = [],
  reference = null,
  selectedId = null,
  onSelect,
  routes: straightRoutes = [],
  roadRoutes = true,
  communityNeed = false,
  height = 380,
  fitKey,
  routeNote,
}: RescueMapViewProps) {
  const { routes, allRoad } = useRoadGeometry(straightRoutes, roadRoutes);
  const areas = useCommunityNeedAreas(communityNeed);
  const [showNeed, setShowNeed] = useState(false);
  const allPoints = useMemo<[number, number][]>(
    () => [
      ...restaurants.map((p) => [p.lat, p.lng] as [number, number]),
      ...organizations.map((p) => [p.lat, p.lng] as [number, number]),
      ...carriers.map((p) => [p.lat, p.lng] as [number, number]),
      ...prospects.map((p) => [p.lat, p.lng] as [number, number]),
      ...straightRoutes.flatMap((r) => r.geometry),
    ],
    [restaurants, organizations, carriers, prospects, straightRoutes],
  );
  const light = useLightTheme();
  const key = fitKey ?? [...restaurants, ...organizations, ...prospects].map((p) => p.id).concat(straightRoutes.map((r) => r.id)).join("|");

  return (
    <div className="map-shell" style={{ height }}>
      <MapContainer center={FIU} zoom={13} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
        {MAPBOX_TOKEN ? (
          <TileLayer
            key={light ? "mb-light" : "mb-dark"}
            url={`https://api.mapbox.com/styles/v1/mapbox/${light ? "light-v11" : "dark-v11"}/tiles/512/{z}/{x}/{y}@2x?access_token=${MAPBOX_TOKEN}`}
            tileSize={512}
            zoomOffset={-1}
            attribution='&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          />
        ) : (
          <TileLayer
            key={light ? "esri-light" : "esri-dark"}
            url={`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/${light ? "World_Light_Gray_Base" : "World_Dark_Gray_Base"}/MapServer/tile/{z}/{y}/{x}`}
            attribution="&copy; Esri &amp; HERE, Garmin, OpenStreetMap contributors, and the GIS user community"
          />
        )}
        <FitBounds points={allPoints} fitKey={key} />
        {showNeed && areas.length > 0 && <CommunityNeedLayer areas={areas} />}

        {routes.map((r) => (
          <RouteLine key={r.id} route={r} />
        ))}
        {routes.flatMap((r) =>
          (r.stops ?? []).map((s, i) => (
            <Marker key={`${r.id}-stop-${i}`} position={[s.lat, s.lng]} icon={numberIcon(String(i + 1))} zIndexOffset={500}>
              <Tooltip direction="top" offset={[0, -10]}>
                {i + 1}. {s.label}
              </Tooltip>
            </Marker>
          )),
        )}
        {restaurants.map((p) => (
          <Marker key={p.id} position={[p.lat, p.lng]} icon={emojiIcon("🍽️", COLORS.restaurant, { newPulse: p.isNew })} zIndexOffset={600}>
            <Tooltip direction="top" offset={[0, -16]}>
              <strong>{p.label}</strong>
              {p.detail ? <div>{p.detail}</div> : null}
            </Tooltip>
          </Marker>
        ))}
        {organizations.map((p) => (
          <Marker key={p.id} position={[p.lat, p.lng]} icon={emojiIcon("🏢", COLORS.org)} zIndexOffset={600}>
            <Tooltip direction="top" offset={[0, -16]}>
              <strong>{p.label}</strong>
              {p.detail ? <div>{p.detail}</div> : null}
            </Tooltip>
          </Marker>
        ))}
        {prospects.map((p) => (
          <CircleMarker
            key={p.id}
            center={[p.lat, p.lng]}
            radius={p.id === selectedId ? 11 : 8}
            eventHandlers={onSelect ? { click: () => onSelect(p.id) } : undefined}
            pathOptions={{ color: COLORS.prospect, weight: p.id === selectedId ? 4 : 3, fillColor: "var(--panel)", fillOpacity: 1 }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              <strong>{p.label}</strong>
              {p.detail ? <div>{p.detail}</div> : null}
            </Tooltip>
          </CircleMarker>
        ))}
        {reference && (
          <CircleMarker center={[reference.lat, reference.lng]} radius={7} pathOptions={{ color: "var(--ink)", weight: 2, fillColor: "var(--panel)", fillOpacity: 1 }}>
            <Tooltip direction="top" offset={[0, -8]} permanent>
              <strong>{reference.label}</strong>
            </Tooltip>
          </CircleMarker>
        )}
        {carriers.map((p) => (
          <GlidingCarrier key={p.id} point={p} />
        ))}
      </MapContainer>
      <div className="absolute right-2 top-2 z-[1000] flex max-w-[70%] flex-wrap justify-end gap-x-3 gap-y-1 rounded-md border border-line bg-panel/90 px-3 py-1.5 text-xs font-semibold text-ink-2 backdrop-blur">
        {restaurants.length > 0 && <Legend color={COLORS.restaurant} label="Restaurant" />}
        {carriers.length > 0 && <Legend color={CARRIER_COLOR.EN_ROUTE} label="Carrier, live" />}
        {organizations.length > 0 && <Legend color={COLORS.org} label="Organization" />}
        {prospects.length > 0 && <Legend color={COLORS.prospect} label="Researched prospect, not a partner" ring />}
        {straightRoutes.length > 0 ? <span>{allRoad ? "Road route: OSRM (OpenStreetMap), no live traffic" : routeNote}</span> : null}
        {showNeed && areas.length > 0 && (
          <>
            <Legend color={NEED_FILL.low} label="Low" />
            <Legend color={NEED_FILL.moderate} label="Mod." />
            <Legend color={NEED_FILL.high} label="High" />
            <Legend color={NEED_FILL.very_high} label="V. high need (Census poverty rate)" />
          </>
        )}
      </div>
      {areas.length > 0 && (
        <button
          type="button"
          onClick={() => setShowNeed((v) => !v)}
          className={`absolute bottom-6 left-2 z-[1000] chip ${showNeed ? "chip-accent" : ""}`}
          style={{ minHeight: 44 }}
          aria-pressed={showNeed}
        >
          Community need: {showNeed ? "on" : "off"}
        </button>
      )}
    </div>
  );
}
