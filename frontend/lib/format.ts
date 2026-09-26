export const miles = (n: number) => `${n.toFixed(1)} mi`;
export const minutes = (n: number) => `${Math.round(n)} min`;

// "48 min" under 90 minutes, "1.5 h" above -- for food-safety windows that can span days
// (shelf-stable food is safe for 48 h) without the metric turning into an ugly four-digit number.
export function shortDuration(totalMinutes: number): { value: string; unit: string } {
  const m = Math.round(totalMinutes);
  if (m < 90) return { value: String(m), unit: "min" };
  const hours = m / 60;
  return { value: hours >= 10 ? String(Math.round(hours)) : hours.toFixed(1), unit: "h" };
}
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

export function defaultDeadline(): string {
  // "pickup before 10 PM" tonight, or three hours from now if it is already late
  const d = new Date();
  const tenPm = new Date(d);
  tenPm.setHours(22, 0, 0, 0);
  const target = tenPm.getTime() - d.getTime() > 45 * 60000 ? tenPm : new Date(d.getTime() + 3 * 3600000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(target.getDate())}T${pad(target.getHours())}:${pad(target.getMinutes())}`;
}
