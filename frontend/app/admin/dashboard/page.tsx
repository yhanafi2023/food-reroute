"use client";
import { useEffect, useState } from "react";
import AppShell, { ErrorNote, LiveStatus, Loading, Stat } from "@/components/AppShell";
import FlowMap from "@/components/FlowMap";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { number, usd } from "@/lib/format";
import type { AdminNetwork, CensusArea, CommunityNeedAreas } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

export default function AdminDashboardPage() {
  const user = useRequireRole("admin");
  const { data, error, refresh, updatedAt } = usePoll<AdminNetwork>(user ? "/admin/network" : null, 5000);
  const [areas, setAreas] = useState<CommunityNeedAreas | null>(null);
  const [showNeed, setShowNeed] = useState(true);
  const [selectedArea, setSelectedArea] = useState<CensusArea | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (user) api<CommunityNeedAreas>("/community-need/areas").then(setAreas).catch(() => undefined);
  }, [user]);

  if (!user) return null;

  const underservedHighNeed = data
    ? data.organizations.filter((o) => o.community_need && (o.community_need.bucket === "high" || o.community_need.bucket === "very_high")
        && (o.current_need ?? o.typical_nightly_need ?? 0) > 0).length
    : 0;

  return (
    <AppShell
      icon="stats"
      title="Network"
      subtitle="Every restaurant, driver and organization, live."
      actions={
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-ghost" disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await api<Record<string, number>>("/admin/jobs/run", { method: "POST" });
                const done = Object.entries(r).filter(([, v]) => v > 0);
                setNote(`Ran scheduled jobs: ${done.map(([k, v]) => `${k} ${v}`).join(", ") || "nothing due"}`);
                refresh();
              } catch (e) { setNote((e as Error).message); } finally { setBusy(false); }
            }}>
            {busy ? "Running..." : "Run scheduled jobs"}
          </button>
        </div>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <LiveStatus updatedAt={updatedAt} error={error} />
        <span className="text-sm text-ink-3">Restaurants, drivers and organizations here are fictional demo accounts.</span>
      </div>
      <ErrorNote message={error} onRetry={refresh} stale={!!data} />
      {note && <div className="alert alert-info" role="status">{note}</div>}
      {!data ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Open rescues" icon="food-box" value={data.stats.open_rescues} />
            <Stat label="Active trips" icon="route" value={data.stats.active_trips} />
            <Stat label="Drivers available" icon="driver" value={`${data.stats.available_volunteers} / ${data.stats.total_volunteers}`} />
            <Stat label="Meals rescued" icon="hot-meal" value={number(data.impact.meals_rescued)} note={data.impact.includes_demo_data ? "Includes demo data" : undefined} />
          </div>

          <section className="panel flex flex-col gap-3 border-l-4" style={{ borderLeftColor: "var(--cyan)" }}>
            <div className="flex items-center justify-between">
              <h3>Community Impact Mode</h3>
              <span className="chip">{showNeed ? "layer on" : "toggle the map layer below"}</span>
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Active rescues" value={data.active_rescues.length} />
              <Stat label="Organizations requesting food" icon="community-org" value={data.organizations.filter((o) => (o.current_need ?? 0) > 0).length} />
              <Stat label="High-need areas underserved" icon="alert" value={underservedHighNeed} note="High/Very High need with an open request" />
              <Stat label="Meals in the network today" value={number(data.active_rescues.reduce((s, r) => s + r.est_meals, 0))} />
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
            <FlowMap
              height={520}
              restaurants={data.restaurants.map((r) => ({ id: `r${r.id}`, lat: r.lat, lng: r.lng, label: r.name, detail: "Restaurant" }))}
              organizations={data.organizations.map((o) => ({
                id: `o${o.id}`, lat: o.lat, lng: o.lng, label: o.name,
                detail: o.community_need ? `${o.community_need.bucket_label} community need (${o.community_need.poverty_rate.toFixed(0)}%)` : "Community need: no data",
              }))}
              drivers={data.volunteers.filter((v) => v.on_active_trip || v.available_now).map((v) => ({
                id: `v${v.id}`, lat: v.lat, lng: v.lng, label: v.name,
                detail: v.on_active_trip ? "On a trip" : "Available",
                status: v.on_active_trip ? "ON_DELIVERY" : "AVAILABLE",
              }))}
              chips={[`${data.active_trips.length} active trips`]}
              communityNeed={areas?.areas ?? []}
              showCommunityNeed={showNeed}
              onToggleCommunityNeed={setShowNeed}
              onSelectArea={setSelectedArea}
              fitKey="network"
            />
            <aside className="flex flex-col gap-4">
              {selectedArea && (
                <section className="panel flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <h3>{selectedArea.bucket_label} Community Need</h3>
                    <button className="text-sm text-ink-3 underline" onClick={() => setSelectedArea(null)}>close</button>
                  </div>
                  <p className="text-sm text-ink-2">{selectedArea.name}</p>
                  <div className="stat"><span className="eyebrow">Census tract poverty rate</span><span className="stat-value">{selectedArea.poverty_rate.toFixed(1)}%</span></div>
                  <p className="text-sm text-ink-3">Estimated population below poverty level: {number(selectedArea.population_below_poverty)} of {number(selectedArea.population)}</p>
                  <p className="text-xs text-ink-3">{areas?.disclaimer}</p>
                </section>
              )}
              <section className="panel flex flex-col gap-3">
                <h3>Open and active rescues</h3>
                {data.active_rescues.length === 0 && <p className="text-ink-3">None right now.</p>}
                {data.active_rescues.map((r) => (
                  <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2 text-sm last:border-0">
                    <span>{r.est_meals} meals · {r.restaurant.name}</span>
                    <span className="chip">{r.status.replace(/_/g, " ")}</span>
                  </div>
                ))}
              </section>
              <section className="panel flex flex-col gap-2">
                <h3>Impact so far</h3>
                <p className="text-sm text-ink-2">
                  {number(data.impact.meals_rescued)} meals · {data.impact.lbs_diverted.toFixed(1)} lbs · {data.impact.deliveries_completed} deliveries
                </p>
                <p className="text-xs text-ink-3">Community value estimate {usd(data.impact.community_value_estimate_usd)} (assumed value per meal). Includes demo data.</p>
              </section>
            </aside>
          </div>
        </>
      )}
    </AppShell>
  );
}
