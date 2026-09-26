// Times are shown in the service area's time zone (Miami), whatever the viewer's device says.
export const TIMEZONE = "America/New_York";

export const number = (n: number) => n.toLocaleString("en-US");

export function time(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TIMEZONE });
}

export function minutesBetween(fromIso: string, toIso: string): number {
  return Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60000);
}

export function relative(targetIso: string | null | undefined, nowIso: string | null | undefined): string {
  if (!targetIso || !nowIso) return "";
  const m = minutesBetween(nowIso, targetIso);
  if (m < -1) return `${-m} min ago`;
  if (m <= 1) return "now";
  if (m < 60) return `in ${m} min`;
  return `in ${Math.floor(m / 60)} h ${m % 60} min`;
}

export const UNIT_LABEL: Record<string, [string, string]> = {
  individual_meal: ["meal", "meals"],
  bag: ["bag", "bags"],
  box: ["box", "boxes"],
  tray: ["tray", "trays"],
  half_pan: ["half pan", "half pans"],
  full_pan: ["full pan", "full pans"],
};

export function qty(n: number, unit: string): string {
  const [one, many] = UNIT_LABEL[unit] ?? [unit, unit];
  return `${n % 1 === 0 ? n : n.toFixed(1)} ${n === 1 ? one : many}`;
}

export const STATUS_LABEL: Record<string, string> = {
  posted: "Looking for a carrier",
  matched: "Carrier assigned",
  en_route_pickup: "On the way to pick up",
  picked_up: "Picked up",
  en_route_dropoff: "On the way to drop off",
  delivered: "Delivered, waiting for receipt",
  received: "Received",
  rejected: "Not accepted",
  expired: "Expired",
  cancelled: "Cancelled",
  reassigned: "Reassigned",
  pending: "Not arrived yet",
  rerouted: "Re-routed",
};

export function statusLabel(s: string): string {
  return STATUS_LABEL[s] ?? s.replace(/_/g, " ");
}

export const CARRIER_LABEL: Record<string, string> = {
  volunteer: "Volunteer",
  waymo_sim: "Simulated autonomous vehicle",
  robot_sim: "Simulated sidewalk robot",
};
