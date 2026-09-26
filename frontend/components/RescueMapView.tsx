"use client";
// React Leaflet map, ported from MapView in 238b63d (dark basemap, emoji badge markers, glowing
// route with moving particles, numbered stops, gliding carrier markers, legend). Fed from the
// current API types through components/RescueMap.tsx, which loads this file with ssr: false.
// Tiles: Mapbox dark when NEXT_PUBLIC_MAPBOX_TOKEN is set, otherwise Esri's keyless dark gray canvas.
import L from "leaflet";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";

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
  routes?: MapRoute[];
  height?: number;
  fitKey?: string;
  routeNote?: string;
}

const COLORS = { restaurant: "var(--m-restaurant)", org: "var(--m-org)", route: "var(--cyan)", muted: "var(--m-offline)" };
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

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <i aria-hidden className="inline-block h-3 w-3 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

export default function RescueMapView({ restaurants = [], organizations = [], carriers = [], routes = [], height = 380, fitKey, routeNote }: RescueMapViewProps) {
  const allPoints = useMemo<[number, number][]>(
    () => [
      ...restaurants.map((p) => [p.lat, p.lng] as [number, number]),
      ...organizations.map((p) => [p.lat, p.lng] as [number, number]),
      ...carriers.map((p) => [p.lat, p.lng] as [number, number]),
      ...routes.flatMap((r) => r.geometry),
    ],
    [restaurants, organizations, carriers, routes],
  );
  const light = useLightTheme();
  const key = fitKey ?? [...restaurants, ...organizations].map((p) => p.id).concat(routes.map((r) => r.id)).join("|");

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
        {carriers.map((p) => (
          <GlidingCarrier key={p.id} point={p} />
        ))}
      </MapContainer>
      <div className="absolute right-2 top-2 z-[1000] flex max-w-[70%] flex-wrap justify-end gap-x-3 gap-y-1 rounded-md border border-line bg-panel/90 px-3 py-1.5 text-xs font-semibold text-ink-2 backdrop-blur">
        {restaurants.length > 0 && <Legend color={COLORS.restaurant} label="Restaurant" />}
        {carriers.length > 0 && <Legend color={CARRIER_COLOR.EN_ROUTE} label="Carrier, live" />}
        {organizations.length > 0 && <Legend color={COLORS.org} label="Organization" />}
        {routeNote ? <span>{routeNote}</span> : null}
      </div>
    </div>
  );
}
