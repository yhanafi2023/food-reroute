"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { CARRIER_LABEL } from "@/lib/format";
import type { MatchingExplanation, PostResult } from "@/lib/types";

// The dispatch sequence from 238b63d, shown after a restaurant posts. Adapted to real data: every
// number and name comes from the post response and the recorded matching explanation
// (GET /rescues/{id}/matching-explanation). Nothing is random, and posting is never delayed for it.
// Steps map onto the lifecycle: created = posted, searching = matching running,
// found = matched (a carrier was assigned) or still posted (FoodFlow keeps retrying).
type Step = "created" | "searching" | "found";
const SCHEDULE: { step: Step; at: number }[] = [
  { step: "created", at: 0 },
  { step: "searching", at: 450 },
  { step: "found", at: 1200 },
];

// Counts up from 0 to `target` over `duration` ms, starting after `delay` ms.
function useCountUp(target: number, duration = 550, delay = 0) {
  const [n, setN] = useState(0);
  useEffect(() => {
    let raf = 0;
    const timer = setTimeout(() => {
      const t0 = performance.now();
      const tick = (now: number) => {
        const f = Math.min((now - t0) / duration, 1);
        setN(Math.round(target * (1 - Math.pow(1 - f, 2))));
        if (f < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }, delay);
    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(raf);
    };
  }, [target, duration, delay]);
  return n;
}

export default function RescueSequence({ result }: { result: PostResult }) {
  const [step, setStep] = useState<Step>("created");
  const [why, setWhy] = useState<MatchingExplanation | null>(null);
  const rescue = result.rescue;

  useEffect(() => {
    const timers = SCHEDULE.map(({ step: s, at }) => setTimeout(() => setStep(s), at));
    return () => timers.forEach(clearTimeout);
  }, [rescue.id]);

  useEffect(() => {
    let stopped = false;
    api<MatchingExplanation>(`/rescues/${rescue.id}/matching-explanation`)
      .then((d) => !stopped && setWhy(d))
      .catch(() => {});
    return () => {
      stopped = true;
    };
  }, [rescue.id]);

  const checked = why ? why.eligible.length + why.ineligible.length : 0;
  const eligible = why ? why.eligible.length : 0;
  const checkedN = useCountUp(checked, 500, 150);
  const eligibleN = useCountUp(eligible, 500, 300);
  const trip = rescue.trips.find((t) => !["cancelled", "reassigned", "expired"].includes(t.status));
  const chosen = new Set(trip ? trip.stops.map((s) => s.organization.id) : []);
  const carrier = trip ? (trip.carrier.type === "volunteer" ? trip.carrier.first_name : CARRIER_LABEL[trip.carrier.type]) : null;

  return (
    <div className="rescue-seq" role="status" aria-live="polite" aria-label="Matching result">
      <span className="rescue-seq-step">
        <span className="rescue-seq-dot" aria-hidden="true" />
        {step === "found" ? (result.matching.matched ? "MATCH FOUND" : "POSTED") : "DISPATCHING"}
      </span>

      {step === "created" && <div className="rescue-seq-headline">Donation #{rescue.id} posted</div>}

      {step !== "created" && (
        <div className="flex flex-col gap-3">
          {step === "searching" && <div className="rescue-seq-headline">Checking organizations...</div>}
          <div className="flex flex-col gap-1.5">
            <div className="rescue-seq-line">
              <span>Organizations checked</span>
              <b className="num">{checkedN}</b>
            </div>
            <div className="rescue-seq-line">
              <span>Eligible for this food</span>
              <b className="num">{eligibleN}</b>
            </div>
            <div className="rescue-seq-line">
              <span>Meals (estimated)</span>
              <b className="num">{rescue.est_meals}</b>
            </div>
          </div>
          {why && why.eligible.length > 0 && (
            <div className="rescue-seq-candidates">
              {why.eligible.map((o, i) => (
                <span key={o.organization_id} className={`rescue-seq-chip ${step === "found" && chosen.has(o.organization_id) ? "is-chosen" : ""}`} style={{ animationDelay: `${i * 80}ms` }}>
                  {o.name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {step === "found" && (
        <div className="flex flex-col gap-1">
          <div className={`rescue-seq-headline ${result.matching.matched ? "rescue-seq-found" : ""}`}>
            {result.matching.matched ? `Match found: ${carrier}` : "No carrier yet"}
          </div>
          <span className="text-sm text-ink-2">
            {result.matching.matched && trip
              ? `${rescue.est_meals} meals from ${rescue.restaurant.name} to ${trip.stops.map((s) => s.organization.name).join(" and ")}.`
              : "FoodFlow retries every 2 minutes and tells you when a carrier is assigned."}
          </span>
        </div>
      )}
    </div>
  );
}
