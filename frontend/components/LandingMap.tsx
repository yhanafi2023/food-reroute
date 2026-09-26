"use client";
import dynamic from "next/dynamic";

// Leaflet touches `window`, so the map only renders in the browser.
const LandingMapView = dynamic(() => import("./LandingMapView"), {
  ssr: false,
  loading: () => <div className="map-shell skeleton h-full" role="status" aria-label="Loading map" />,
});

// Height comes from .landing-map-frame (shorter on phones).
export default function LandingMap() {
  return <div className="landing-map-frame"><LandingMapView /></div>;
}
