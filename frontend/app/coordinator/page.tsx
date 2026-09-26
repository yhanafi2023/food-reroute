"use client";
import { useState } from "react";
import RescueMap from "@/components/RescueMap";
import { RescueCard } from "@/components/RescueCard";
import { Shell } from "@/components/Shell";
import { Empty, ErrorNote, Loading } from "@/components/States";
import WhyThisAssignment from "@/components/WhyThisAssignment";
import { useWorkspace } from "@/lib/auth";
import { qty, statusLabel } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";
import { useServerNow } from "@/lib/useServerNow";
import type { Rescue } from "@/lib/types";

const FINAL = ["received", "cancelled", "expired", "rejected"];

export default function CoordinatorPage() {
  const user = useWorkspace("coordinator");
  const now = useServerNow();
  const { data, error, refresh } = usePoll<Rescue[]>(user ? "/rescues" : null, 3000);
  const [show, setShow] = useState<"active" | "all">("active");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  if (!user) return null;
  const rows = (data ?? []).filter((r) => !r.is_draft && (show === "all" || !FINAL.includes(r.status)));
  const selected = rows.find((r) => r.id === selectedId) ?? rows[0] ?? null;
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
      {data ? <RescueMap rescues={rows.filter((r) => !FINAL.includes(r.status))} height={420} /> : null}
      {data && rows.length === 0 ? <Empty title="No active rescues">New posts show up here as soon as a restaurant posts.</Empty> : null}
      {rows.length ? (
        <div className="grid-2" style={{ alignItems: "start" }}>
          <section aria-labelledby="list-title" className="stack">
            <h2 id="list-title">List</h2>
            <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0, gap: "var(--s-2)" }}>
              {rows.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    className={`panel panel-tight row ${selected?.id === r.id ? "panel-accent" : ""}`}
                    style={{ width: "100%", justifyContent: "space-between", cursor: "pointer", color: "var(--ink)", textAlign: "left" }}
                    aria-pressed={selected?.id === r.id}
                    onClick={() => setSelectedId(r.id)}
                  >
                    <span>
                      <strong>#{r.id}</strong> {r.restaurant.name}: {qty(r.quantity, r.unit)}
                    </span>
                    <span className="chip">{statusLabel(r.status)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
          {selected ? (
            <section aria-label="Details" className="stack">
              <h2>Details</h2>
              <RescueCard rescue={selected} now={now} />
              <WhyThisAssignment rescue={selected} />
            </section>
          ) : null}
        </div>
      ) : null}
    </Shell>
  );
}
