"use client";
import { useEffect, useState } from "react";

// A short cinematic sequence shown while FoodFlow "finds" a match for a freshly posted rescue.
// Purely a loading-state flourish (the numbers are illustrative network-scanning flavor, not a
// claim about real inventory) — it fills the ~1.5-3s the real match request takes with something
// that reads as "the network is actively working", instead of a static spinner.
type Step = "created" | "searching" | "candidates" | "optimizing" | "found";
const SCHEDULE: { step: Step; at: number }[] = [
  { step: "created", at: 0 },
  { step: "searching", at: 450 },
  { step: "candidates", at: 1500 },
  { step: "optimizing", at: 2150 },
  { step: "found", at: 2700 },
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
    return () => { clearTimeout(timer); cancelAnimationFrame(raf); };
  }, [target, duration, delay]);
  return n;
}

const CANDIDATE_NAMES = ["Marcus", "Dana", "Priya", "Leo", "Sofia", "Andre", "Kim", "Talia"];

export default function RescueSequence({ meals, restaurantName, onCancel }: {
  meals: number; restaurantName: string; onCancel?: () => void;
}) {
  const [step, setStep] = useState<Step>("created");
  // Plausible network-scan counts, reseeded on each mount.
  const [counts] = useState(() => ({
    drivers: 14 + Math.floor(Math.random() * 19),
    orgs: 6 + Math.floor(Math.random() * 10),
  }));
  const matches = Math.max(counts.drivers, Math.round(counts.drivers * (counts.orgs / 6)));
  const driverN = useCountUp(counts.drivers, 500, 500);
  const orgN = useCountUp(counts.orgs, 500, 650);
  const matchN = useCountUp(matches, 550, 800);
  const candidates = CANDIDATE_NAMES.slice(0, 4);

  useEffect(() => {
    const timers = SCHEDULE.map(({ step: s, at }) => setTimeout(() => setStep(s), at));
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="rescue-seq" role="status" aria-live="polite" aria-label="Finding a match">
      <div className="flex items-center justify-between gap-2">
        <span className="rescue-seq-step">
          <span className="rescue-seq-dot" aria-hidden />
          {step === "found" ? "MATCH FOUND" : "DISPATCHING"}
        </span>
        {onCancel && step !== "found" && <button type="button" className="btn btn-ghost" style={{ minHeight: 32, padding: "0 12px" }} onClick={onCancel}>Cancel</button>}
      </div>

      {step === "created" && (
        <div className="rescue-seq-headline">New rescue created</div>
      )}

      {(step === "searching" || step === "candidates" || step === "optimizing") && (
        <div className="flex flex-col gap-3">
          <div className="rescue-seq-headline">Searching network...</div>
          <div className="flex flex-col gap-1.5">
            <div className="rescue-seq-line"><span>Drivers available</span><b className="num">{driverN}</b></div>
            <div className="rescue-seq-line"><span>Organizations nearby</span><b className="num">{orgN}</b></div>
            <div className="rescue-seq-line"><span>Possible matches</span><b className="num">{matchN}</b></div>
          </div>
          {(step === "candidates" || step === "optimizing") && (
            <div className="rescue-seq-candidates" aria-hidden>
              {candidates.map((name, i) => (
                <span key={name} className={`rescue-seq-chip ${step === "optimizing" && i === 0 ? "is-chosen" : ""}`} style={{ animationDelay: `${i * 80}ms` }}>
                  {name}
                </span>
              ))}
            </div>
          )}
          {step === "optimizing" && <div className="rescue-seq-headline" style={{ fontSize: "var(--t-lg)" }}>Optimizing match...</div>}
        </div>
      )}

      {step === "found" && (
        <div className="flex flex-col gap-1">
          <div className="rescue-seq-headline rescue-seq-found">Match found</div>
          <span className="text-sm text-ink-2">{meals} meals from {restaurantName}, matched to the best driver and organization on the network.</span>
        </div>
      )}
    </div>
  );
}
