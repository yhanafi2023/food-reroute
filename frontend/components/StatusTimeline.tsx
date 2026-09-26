import { clock } from "@/lib/format";
import type { Trip, TripStatus } from "@/lib/types";

export const TRIP_STEPS: { status: TripStatus; label: string }[] = [
  { status: "matched", label: "Matched with a carrier" },
  { status: "en_route_pickup", label: "Heading to restaurant" },
  { status: "picked_up", label: "Food picked up" },
  { status: "en_route_dropoff", label: "Delivering" },
  { status: "delivered", label: "Delivered" },
  { status: "received", label: "Confirmed by organization" },
];
const EXIT_LABEL: Partial<Record<TripStatus, string>> = {
  cancelled: "Cancelled", expired: "Expired", rejected: "No organization could take it", reassigned: "Reassigned",
};

// The transit line: every trip status is a numbered stop. Falls back to a plain
// alert for an exit status (cancelled/expired/rejected/reassigned) that isn't on the line.
export default function StatusTimeline({ trip }: { trip: Trip }) {
  const current = TRIP_STEPS.findIndex((s) => s.status === trip.status);
  if (current === -1) {
    return <div className="alert alert-bad" role="status">{EXIT_LABEL[trip.status] ?? trip.status}</div>;
  }
  return (
    <ol className="transit" aria-label="Trip status">
      {TRIP_STEPS.map((step, i) => {
        const state = i < current ? "done" : i === current ? (step.status === "received" ? "done" : "now") : "";
        const time = step.status === "en_route_pickup" ? trip.started_at
          : step.status === "received" ? trip.finished_at : null;
        return (
          <li key={step.status} className={state} aria-current={i === current ? "step" : undefined}>
            <span className="dot">{i < current || (i === current && step.status === "received") ? "✓" : i + 1}</span>
            <span className="label flex flex-wrap items-center justify-between gap-2">
              {step.label}
              {time && <span className="mono text-xs text-ink-3">{clock(time)}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
