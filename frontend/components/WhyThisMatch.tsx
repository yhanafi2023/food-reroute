import type { Breakdown, Candidate } from "@/lib/types";

const TERMS: { key: keyof Breakdown; label: string; explain: string }[] = [
  { key: "distance", label: "Distance", explain: "Miles to the restaurant plus the drop off route" },
  { key: "eta", label: "ETA", explain: "Minutes door to door (x0.1)" },
  { key: "urgency", label: "Urgency", explain: "Extra weight on ETA as the pickup deadline gets close" },
  { key: "demand_fit", label: "Demand fit", explain: "Share of meals that meet a real open need" },
  { key: "priority", label: "Priority", explain: "HIGH and MEDIUM need organizations served" },
];

// Diverging bars around zero: costs (raise the score) extend right, bonuses (lower it) extend left.
// Lower total score wins. Every bar also prints its signed value, so color is never the only cue.
export default function WhyThisMatch({ candidates, reasons }: { candidates: Candidate[]; reasons?: string[] }) {
  if (!candidates.length) return null;
  const scale = Math.max(1, ...candidates.flatMap((c) => TERMS.map((t) => Math.abs(c.breakdown[t.key]))));
  return (
    <section className="panel flex flex-col gap-4" aria-labelledby="why-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="why-title">Why this match?</h3>
        <span className="text-sm text-ink-3">Top {candidates.length} options. Lower score wins.</span>
      </div>
      <div className="flex flex-col gap-3">
        {candidates.map((c, idx) => {
          const winner = idx === 0;
          return (
            <article key={`${c.driver_name}-${idx}`}
              className={`flex flex-col gap-3 rounded-lg border p-4 ${winner ? "border-accent bg-wash" : "border-line"}`}
              aria-label={`Option ${idx + 1}: ${c.driver_name}, score ${c.score.toFixed(1)}${winner ? ", chosen" : ""}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className={`chip ${winner ? "chip-accent" : ""}`}>{winner ? "CHOSEN" : `OPTION ${idx + 1}`}</span>
                  <strong>{c.driver_name}</strong>
                </div>
                <span className="mono num text-sm font-bold">score {c.score.toFixed(1)}</span>
              </div>
              <p className="text-sm text-ink-2">{c.stops_summary}</p>
              <div className="grid gap-1" role="table" aria-label={`Score breakdown for ${c.driver_name}`}>
                {TERMS.map((t) => {
                  const v = c.breakdown[t.key];
                  const width = `${(Math.abs(v) / scale) * 50}%`;
                  const cost = v > 0;
                  return (
                    <div key={t.key} role="row" className="grid grid-cols-[96px_1fr_88px] items-center gap-2 text-sm" title={`${t.label}: ${t.explain}`}>
                      <span role="rowheader" className="text-ink-2">{t.label}</span>
                      <span role="cell" className="relative h-3" aria-hidden>
                        <span className="absolute inset-y-0 left-1/2 w-px bg-ink-3" />
                        {v !== 0 && (
                          <span className="absolute inset-y-0 rounded"
                            style={{ width, left: cost ? "calc(50% + 2px)" : undefined, right: cost ? undefined : "calc(50% + 2px)",
                              background: cost ? "var(--ink-3)" : "var(--cyan)" }} />
                        )}
                      </span>
                      <span role="cell" className="mono num text-right text-xs text-ink-2">
                        {v > 0 ? "+" : ""}{v.toFixed(1)} {v === 0 ? "" : cost ? "cost" : "bonus"}
                      </span>
                    </div>
                  );
                })}
              </div>
            </article>
          );
        })}
      </div>
      {reasons && reasons.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {reasons.map((r) => <li key={r} className="flex gap-2"><span aria-hidden className="text-accent">●</span>{r}</li>)}
        </ul>
      )}
    </section>
  );
}
