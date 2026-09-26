"use client";
// "Why this assignment?" Renders only what the backend recorded when it matched this donation
// (GET /rescues/{id}/matching-explanation): the eligibility check per organization with coded
// reasons, and the carrier choice in plain words. Layout and styling ported from WhyThisMatch in 238b63d.
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { CARRIER_LABEL, time } from "@/lib/format";
import type { MatchingExplanation, Rescue } from "@/lib/types";
import { activeTrip } from "./RescueCard";

export default function WhyThisAssignment({ rescue }: { rescue: Rescue }) {
  const [data, setData] = useState<MatchingExplanation | null>(null);
  const [error, setError] = useState("");
  const trip = activeTrip(rescue);
  const tripKey = trip ? `${trip.id}:${trip.status}` : "none";

  useEffect(() => {
    let stopped = false;
    api<MatchingExplanation>(`/rescues/${rescue.id}/matching-explanation`)
      .then((d) => !stopped && setData(d))
      .catch((e) => !stopped && setError((e as Error).message));
    return () => {
      stopped = true;
    };
  }, [rescue.id, tripKey]);

  if (error) return <p className="small muted">Explanation unavailable: {error}</p>;
  if (!data) return null;
  const chosenOrgs = new Set(trip ? trip.stops.map((s) => s.organization.id) : []);
  const recordedTrip = data.trips.find((t) => t.id === trip?.id) ?? data.trips[data.trips.length - 1];
  const eligible = [...data.eligible].sort((a, b) => Number(chosenOrgs.has(b.organization_id)) - Number(chosenOrgs.has(a.organization_id)));

  return (
    <section className="panel flex flex-col gap-4" aria-label={`Why this assignment for donation ${rescue.id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3>Why this assignment?</h3>
        <span className="text-sm text-ink-3">Recorded at matching (attempt {data.attempt ?? 0})</span>
      </div>
      {recordedTrip ? (
        <article className="flex flex-col gap-2 rounded-lg border border-accent bg-wash p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip chip-accent">CARRIER</span>
            <strong>{CARRIER_LABEL[recordedTrip.mode] ?? recordedTrip.mode}</strong>
            {recordedTrip.simulated ? <span className="chip chip-warn">Simulated</span> : null}
          </div>
          <p className="text-sm text-ink-2">{recordedTrip.mode_reason}</p>
        </article>
      ) : (
        <p className="text-sm text-ink-2">No carrier assigned yet.</p>
      )}
      <div className="flex flex-col gap-3" role="list" aria-label="Organizations checked">
        {eligible.map((o) => {
          const chosen = chosenOrgs.has(o.organization_id);
          return (
            <article key={o.organization_id} role="listitem" className={`flex flex-col gap-1 rounded-lg border p-4 ${chosen ? "border-accent bg-wash" : "border-line"}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`chip ${chosen ? "chip-accent" : "chip-good"}`}>{chosen ? "CHOSEN" : "ELIGIBLE"}</span>
                <strong>{o.name}</strong>
              </div>
              {o.estimated_arrival ? <p className="text-sm text-ink-2">Estimated arrival {time(o.estimated_arrival)}</p> : null}
            </article>
          );
        })}
        {data.ineligible.map((o) => (
          <article key={o.organization_id} role="listitem" className="flex flex-col gap-1 rounded-lg border border-line p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="chip">NOT ELIGIBLE</span>
              <strong>{o.name}</strong>
            </div>
            <ul className="flex flex-col gap-1 text-sm">
              {o.reasons.map((r) => (
                <li key={r.code} className="flex gap-2">
                  <span aria-hidden className="text-cyan">
                    ●
                  </span>
                  {r.text}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
