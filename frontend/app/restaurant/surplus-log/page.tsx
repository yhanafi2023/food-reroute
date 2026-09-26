"use client";
import AppShell, { ErrorNote, Loading } from "@/components/AppShell";
import SurplusLog from "@/components/SurplusLog";
import { useRequireRole } from "@/lib/auth";
import type { SurplusLogPayload } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";
import { useState } from "react";

export default function RestaurantSurplusLogPage() {
  const user = useRequireRole(["restaurant_staff", "restaurant_manager"]);
  const { data, error, refresh } = usePoll<SurplusLogPayload>(user ? "/restaurants/me/surplus-log" : null, 30000);
  const [saved, setSaved] = useState<SurplusLogPayload | null>(null);
  if (!user) return null;
  const current = saved ?? data;
  return (
    <AppShell title="Surplus log" subtitle="Seven days of closing-time counts tell FoodFlow how often to schedule pickups and how much to plan for.">
      <ErrorNote message={error} onRetry={refresh} stale={!!current} />
      {!current ? <Loading what="surplus log" rows={1} /> : (
        <SurplusLog path="/restaurants/me/surplus-log" data={current} onChange={(d) => { setSaved(d); refresh(); }}
          who="Each day at closing, a staff member records how much safe food was left and what happened to it." />
      )}
    </AppShell>
  );
}
