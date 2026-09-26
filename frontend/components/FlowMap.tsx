"use client";
import dynamic from "next/dynamic";
import type { MapViewProps } from "./MapView";

// Leaflet touches `window`, so the map only renders in the browser.
const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div className="map-shell grid place-items-center text-ink-3" style={{ height: 380 }}>Loading map...</div>,
});

export default function FlowMap(props: MapViewProps) {
  return <MapView {...props} />;
}

export type { DriverState, MapPoint, MapRoute, Mover } from "./MapView";
