import type { DeliveryStatus } from "./types";

export const miles = (n: number) => `${n.toFixed(1)} mi`;
export const minutes = (n: number) => `${Math.round(n)} min`;
export const number = (n: number) => n.toLocaleString("en-US");
export const usd = (n: number) => n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function minutesUntil(iso: string): number {
  return Math.round((new Date(iso).getTime() - Date.now()) / 60000);
}

export function until(iso: string): string {
  const m = minutesUntil(iso);
  if (m <= 0) return "past due";
  if (m < 60) return `in ${m} min`;
  const h = Math.floor(m / 60);
  return `in ${h} h ${m % 60} min`;
}

export const DELIVERY_STEPS: { status: DeliveryStatus; label: string; action: string }[] = [
  { status: "HEADING_TO_RESTAURANT", label: "Heading to restaurant", action: "Accept" },
  { status: "ARRIVED_AT_RESTAURANT", label: "Arrived at restaurant", action: "I arrived at the restaurant" },
  { status: "PICKED_UP", label: "Food picked up", action: "I picked up the food" },
  { status: "DELIVERING", label: "Delivering", action: "Start delivering" },
  { status: "DELIVERED", label: "Delivered", action: "Mark delivered" },
  { status: "CONFIRMED", label: "Confirmed by organizations", action: "Waiting for confirmation" },
];

export function nextStep(status: DeliveryStatus) {
  const i = DELIVERY_STEPS.findIndex((s) => s.status === status);
  return i >= 0 && i < 4 ? DELIVERY_STEPS[i + 1] : null;
}

export function defaultDeadline(): string {
  // "pickup before 10 PM" tonight, or three hours from now if it is already late
  const d = new Date();
  const tenPm = new Date(d);
  tenPm.setHours(22, 0, 0, 0);
  const target = tenPm.getTime() - d.getTime() > 45 * 60000 ? tenPm : new Date(d.getTime() + 3 * 3600000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(target.getDate())}T${pad(target.getHours())}:${pad(target.getMinutes())}`;
}
