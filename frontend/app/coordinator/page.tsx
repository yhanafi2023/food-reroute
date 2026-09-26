"use client";
import { useState } from "react";
import { RescueCard } from "@/components/RescueCard";
import { Shell } from "@/components/Shell";
import { Empty, ErrorNote, Loading } from "@/components/States";
import { useWorkspace } from "@/lib/auth";
import { usePoll } from "@/lib/usePoll";
import { useServerNow } from "@/lib/useServerNow";
import type { Rescue } from "@/lib/types";

const FINAL = ["received", "cancelled", "expired", "rejected"];

export default function CoordinatorPage() {
  const user = useWorkspace("coordinator");
  const now = useServerNow();
  const { data, error, refresh } = usePoll<Rescue[]>(user ? "/rescues" : null, 3000);
  const [show, setShow] = useState<"active" | "all">("active");
  if (!user) return null;
  const rows = (data ?? []).filter((r) => !r.is_draft && (show === "all" || !FINAL.includes(r.status)));
  return (
    <Shell workspace="coordinator">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Rescues</h1>
        <div className="seg" role="group" aria-label="Show">
          <button type="button" aria-pressed={show === "active"} onClick={() => setShow("active")}>
            Active
          </button>
          <button type="button" aria-pressed={show === "all"} onClick={() => setShow("all")}>
            All
          </button>
        </div>
      </div>
      {error && !data ? <ErrorNote message={error} onRetry={refresh} /> : null}
      {!data && !error ? <Loading label="Loading rescues" /> : null}
      {data && rows.length === 0 ? <Empty title="No active rescues">New posts show up here as soon as a restaurant posts.</Empty> : null}
      <div className="grid-2" style={{ alignItems: "start" }}>
        {rows.map((r) => (
          <RescueCard key={r.id} rescue={r} now={now} />
        ))}
      </div>
    </Shell>
  );
}
