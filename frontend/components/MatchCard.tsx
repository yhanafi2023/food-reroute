"use client";
import DeliveryMap from "./DeliveryMap";
import WhyThisMatch from "./WhyThisMatch";
import { minutesUntil, shortDuration } from "@/lib/format";
import type { MatchingExplanation, Rescue, Trip } from "@/lib/types";

function marginClass(margin: number) {
  if (margin >= 20) return "is-good";
  if (margin >= 10) return "is-warn";
  return "is-bad";
}

export default function MatchCard({ rescue, trip, explanation, showMap = true }: {
  rescue: Rescue; trip: Trip; explanation: MatchingExplanation | null; showMap?: boolean;
}) {
  const pickupEta = Math.max(0, minutesUntil(trip.eta_pickup));
  const foodDeadline = Math.max(0, minutesUntil(rescue.safe_until));
  const safetyMargin = Math.round(foodDeadline - pickupEta);
  const chosenOrgIds = new Set(trip.stops.map((s) => s.organization.id));
  const carrierName = trip.carrier.type === "volunteer" ? trip.carrier.first_name : trip.carrier.label;
  const etaShown = shortDuration(pickupEta);
  const marginShown = shortDuration(Math.abs(safetyMargin));

  return (
    <section className="flex flex-col gap-3 match-card-enter" aria-label="Match found">
      {/* One thin summary line -- the map below is the point. */}
      <div className="panel panel-tight panel-accent flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className="eyebrow inline-flex items-center gap-2" style={{ color: "var(--good)" }}>
          <i aria-hidden className="inline-block h-2 w-2 rounded-full bg-good" />
          Match found
        </span>
        <strong>{rescue.est_meals} meals</strong>
        <span className="text-ink-2">{rescue.restaurant.name} → {carrierName} → {trip.stops.map((s) => s.organization.name).join(", ")}</span>
        <span className="ml-auto flex flex-wrap gap-2 text-xs text-ink-3">
          <span>ETA {etaShown.value}{etaShown.unit}</span>
          <span className={marginClass(safetyMargin) === "is-bad" ? "text-bad" : undefined}>margin {marginShown.value}{marginShown.unit}</span>
        </span>
      </div>
      {showMap && <DeliveryMap rescue={rescue} trip={trip} height={480} />}
      {explanation && explanation.eligible.length > 0 && (
        <details className="panel panel-tight">
          <summary className="cursor-pointer select-none text-sm font-semibold text-ink-2">Why this match? ({explanation.eligible.length} organization{explanation.eligible.length === 1 ? "" : "s"} considered)</summary>
          <div className="pt-3">
            <WhyThisMatch candidates={explanation.eligible} chosenOrgIds={chosenOrgIds} />
          </div>
        </details>
      )}
    </section>
  );
}
