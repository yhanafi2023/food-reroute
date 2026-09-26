"use client";
import { TopNav } from "@/components/AppShell";
import Icon from "@/components/Icon";
import { number, usd } from "@/lib/format";
import type { Impact } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

export default function ImpactPage() {
  const { data, error } = usePoll<Impact>("/impact", 5000);
  return (
    <>
    <TopNav />
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-6">
      <section className="flex flex-col gap-3">
        <span className="eyebrow">Impact</span>
        <h1>Food moved from kitchens to communities.</h1>
        <p className="alert alert-info max-w-[70ch]">
          Only deliveries confirmed by a receiving organization count here.{data?.includes_demo_data
            ? " This demo environment's fictional seeded accounts and history are currently included."
            : ""}
        </p>
      </section>
      {error && <div className="alert alert-bad" role="alert">{error}</div>}
      {!data ? <div className="panel text-ink-2" role="status">Loading impact...</div> : (
        <>
          <section className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
            <div className="panel flex flex-col justify-between gap-6 bg-accent" style={{ background: "var(--accent)", borderColor: "var(--accent)" }}>
              <span className="flex items-center justify-between gap-3">
                <span className="eyebrow" style={{ color: "#dbe6fb" }}>Meals rescued (real, confirmed)</span>
                <Icon name="hot-meal" size={56} className="rounded-2xl bg-white/90 p-1.5" />
              </span>
              <span className="num text-white" style={{ fontFamily: "var(--ff-display)", fontSize: "clamp(64px, 10vw, 120px)", lineHeight: 1, fontWeight: 750 }}>
                {number(data.meals_rescued)}
              </span>
              <span style={{ color: "#dbe6fb" }}>from {data.restaurants} restaurants to {data.organizations} community organizations</span>
            </div>
            <dl className="panel grid grid-cols-2 gap-6">
              <div className="flex flex-col gap-1"><dt className="eyebrow flex items-center gap-2"><Icon name="scale" size={26} />Lbs diverted from waste</dt><dd className="stat-value">{number(data.lbs_diverted)}</dd></div>
              <div className="flex flex-col gap-1"><dt className="eyebrow flex items-center gap-2"><Icon name="van" size={26} />Deliveries completed</dt><dd className="stat-value">{data.deliveries_completed}</dd></div>
              <div className="flex flex-col gap-1"><dt className="eyebrow flex items-center gap-2"><Icon name="eta" size={26} />Avg delivery time</dt><dd className="stat-value">{Math.round(data.avg_delivery_minutes)} min</dd></div>
              <div className="flex flex-col gap-1">
                <dt className="eyebrow flex items-center gap-2"><Icon name="community" size={26} />Community value</dt>
                <dd className="stat-value">{usd(data.community_value_estimate_usd)}</dd>
                <dd className="text-xs text-ink-3">Estimate: meals x an assumed value per meal (MEAL_VALUE_USD)</dd>
              </div>
            </dl>
          </section>
          <p className="max-w-[70ch] text-sm text-ink-3">
            Meals count only after the receiving organization confirms the drop off. Delivery time runs from the driver
            accepting to the last drop off.
          </p>
        </>
      )}
    </div>
    </>
  );
}
