import { DELIVERY_STEPS, clock } from "@/lib/format";
import type { Delivery } from "@/lib/types";

// The transit line: every delivery status is a numbered stop.
export default function StatusTimeline({ delivery }: { delivery: Delivery }) {
  const current = DELIVERY_STEPS.findIndex((s) => s.status === delivery.status);
  const at = new Map(delivery.status_history.map((h) => [h.status, h.at]));
  return (
    <ol className="transit" aria-label="Delivery status">
      {DELIVERY_STEPS.map((step, i) => {
        const state = i < current ? "done" : i === current ? (step.status === "CONFIRMED" ? "done" : "now") : "";
        const time = at.get(step.status);
        return (
          <li key={step.status} className={state} aria-current={i === current ? "step" : undefined}>
            <span className="dot">{i < current || (i === current && step.status === "CONFIRMED") ? "✓" : i + 1}</span>
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
