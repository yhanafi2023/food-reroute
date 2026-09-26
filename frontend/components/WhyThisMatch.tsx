import type { EligibleOrg } from "@/lib/types";

const BUCKET_CLASS: Record<string, string> = {
  low: "", moderate: "", high: "chip-warn", very_high: "chip-bad",
};

// Diverging bars: each named component (distance/urgency/demand/capacity/community need)
// is already normalized to [0, 1], so every candidate's bar uses the same scale.
export default function WhyThisMatch({ candidates, chosenOrgIds }: { candidates: EligibleOrg[]; chosenOrgIds: Set<number> }) {
  if (!candidates.length) return null;
  const ranked = [...candidates].sort((a, b) => a.rank - b.rank);
  const TERMS: { key: keyof EligibleOrg["score"]; label: string }[] = [
    { key: "distance_score", label: "Distance" },
    { key: "urgency_score", label: "Urgency" },
    { key: "demand_score", label: "Demand fit" },
    { key: "capacity_score", label: "Capacity" },
    { key: "community_need_score", label: "Community need" },
  ];
  return (
    <section className="flex flex-col gap-3" aria-label="Why this match">
      <div className="flex flex-col gap-3">
        {ranked.map((c) => {
          const chosen = chosenOrgIds.has(c.organization_id);
          const need = c.score.community_need;
          return (
            <article key={c.organization_id}
              className={`flex flex-col gap-3 rounded-lg border p-4 ${chosen ? "border-accent bg-wash" : "border-line"}`}
              aria-label={`${chosen ? "Chosen: " : ""}${c.name}, score ${c.score.total.toFixed(2)}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className={`chip ${chosen ? "chip-accent" : ""}`}>{chosen ? "CHOSEN" : `#${c.rank}`}</span>
                  <strong>{c.name}</strong>
                  {need && <span className={`chip ${BUCKET_CLASS[need.bucket]}`}>{need.bucket_label} community need</span>}
                </div>
                <span className="mono num text-sm font-bold">score {c.score.total.toFixed(2)}</span>
              </div>
              {c.why.length > 0 && (
                <ul className="flex flex-col gap-1 text-sm">
                  {c.why.map((w) => <li key={w} className="flex gap-2"><span aria-hidden className="text-good">✓</span>{w}</li>)}
                </ul>
              )}
              <div className="grid gap-1" role="table" aria-label={`Score breakdown for ${c.name}`}>
                {TERMS.map((t) => {
                  const v = c.score[t.key] as number;
                  return (
                    <div key={t.key} role="row" className="grid grid-cols-[112px_1fr_48px] items-center gap-2 text-sm">
                      <span role="rowheader" className="text-ink-2">{t.label}</span>
                      <span role="cell" className="relative h-3 rounded bg-wash" aria-hidden>
                        <span className="absolute inset-y-0 left-0 rounded bg-cyan" style={{ width: `${v * 100}%` }} />
                      </span>
                      <span role="cell" className="mono num text-right text-xs text-ink-2">{v.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
