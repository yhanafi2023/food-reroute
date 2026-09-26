"use client";
import FlowMap from "./FlowMap";
import { miles, minutes } from "@/lib/format";
import type { Delivery } from "@/lib/types";

export function deliveryMapProps(d: Delivery) {
  return {
    restaurants: [{ id: `r${d.restaurant.id}`, lat: d.restaurant.lat, lng: d.restaurant.lng, label: d.restaurant.name, detail: "Pickup" }],
    drivers: [{ id: `d${d.driver_id}`, lat: d.driver_location.lat, lng: d.driver_location.lng, label: d.driver_name, detail: d.status.replace(/_/g, " ").toLowerCase() }],
    organizations: d.stops.map((s) => ({ id: `o${s.organization_id}`, lat: s.lat, lng: s.lng, label: s.name, detail: `${s.meals} meals` })),
    routes: [{ id: `del${d.id}`, geometry: d.route.geometry, stops: d.stops.map((s) => ({ lat: s.lat, lng: s.lng, label: s.name })) }],
    chips: [miles(d.route.distance_miles), `ETA ${minutes(d.route.eta_minutes)}`, d.route.source === "offline" ? "offline estimate" : `${d.route.source} route`],
  };
}

export default function DeliveryMap({ delivery, height = 340 }: { delivery: Delivery; height?: number }) {
  return <FlowMap {...deliveryMapProps(delivery)} height={height} fitKey={`del${delivery.id}`} />;
}
