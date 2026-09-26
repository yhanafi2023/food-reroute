"use client";
import { useEffect, useRef, useState } from "react";
import RescueMap from "@/components/RescueMap";
import { RescueCard } from "@/components/RescueCard";
import RescueSequence from "@/components/RescueSequence";
import WhyThisAssignment from "@/components/WhyThisAssignment";
import { Shell } from "@/components/Shell";
import { Empty, ErrorNote, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/auth";
import { time } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";
import { serverNowMs, useServerNow } from "@/lib/useServerNow";
import type { PostResult, Rescue } from "@/lib/types";

const UNITS = [
  ["individual_meal", "Meals"],
  ["tray", "Trays"],
  ["half_pan", "Half pans"],
  ["full_pan", "Full pans"],
  ["box", "Boxes"],
  ["bag", "Bags"],
] as const;
const CATEGORIES = [
  ["hot", "Hot"],
  ["cold", "Cold"],
  ["frozen", "Frozen"],
  ["shelf_stable", "Shelf stable"],
] as const;
const WITHIN = [60, 90, 120];

function DonateForm({ onPosted }: { onPosted: (r: PostResult) => void }) {
  const openedAt = useRef<number>(0);
  const [quantity, setQuantity] = useState(3);
  const [unit, setUnit] = useState<string>("tray");
  const [category, setCategory] = useState<string>("hot");
  const [within, setWithin] = useState(90);
  const [attested, setAttested] = useState(false);
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    openedAt.current = serverNowMs();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<PostResult>("/rescues", {
        method: "POST",
        body: {
          quantity,
          unit,
          category,
          attested,
          description,
          pickup_deadline: new Date(serverNowMs() + within * 60000).toISOString(),
          form_opened_at: new Date(openedAt.current || serverNowMs()).toISOString(),
        },
      });
      onPosted(res);
      setAttested(false);
      setDescription("");
      openedAt.current = serverNowMs();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="panel stack" onSubmit={submit} aria-labelledby="donate-title">
      <h2 id="donate-title">Donate surplus food</h2>
      {error ? <ErrorNote message={error} /> : null}
      <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, gap: "var(--s-2)" }}>
        <legend className="field">
          <span>How much</span>
        </legend>
        <div className="row">
          <button type="button" className="btn btn-ghost" aria-label="One less" onClick={() => setQuantity((q) => Math.max(1, q - 1))}>
            −
          </button>
          <input
            className="input"
            style={{ width: 96, textAlign: "center" }}
            type="number"
            min={1}
            max={1000}
            aria-label="Quantity"
            value={quantity}
            onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))}
          />
          <button type="button" className="btn btn-ghost" aria-label="One more" onClick={() => setQuantity((q) => Math.min(1000, q + 1))}>
            +
          </button>
        </div>
        <div className="seg" role="group" aria-label="Unit" style={{ flexWrap: "wrap" }}>
          {UNITS.map(([v, l]) => (
            <button key={v} type="button" aria-pressed={unit === v} onClick={() => setUnit(v)}>
              {l}
            </button>
          ))}
        </div>
      </fieldset>
      <div className="stack" style={{ gap: "var(--s-2)" }}>
        <span className="small" style={{ fontWeight: 600, color: "var(--ink-2)" }}>
          Food type
        </span>
        <div className="seg" role="group" aria-label="Food type" style={{ flexWrap: "wrap" }}>
          {CATEGORIES.map(([v, l]) => (
            <button key={v} type="button" aria-pressed={category === v} onClick={() => setCategory(v)}>
              {l}
            </button>
          ))}
        </div>
      </div>
      <div className="stack" style={{ gap: "var(--s-2)" }}>
        <span className="small" style={{ fontWeight: 600, color: "var(--ink-2)" }}>
          Pick up within
        </span>
        <div className="seg" role="group" aria-label="Pick up within">
          {WITHIN.map((m) => (
            <button key={m} type="button" aria-pressed={within === m} onClick={() => setWithin(m)}>
              {m < 120 ? `${m} min` : "2 hours"}
            </button>
          ))}
        </div>
        <span className="small muted">Pickup by {time(new Date(serverNowMs() + within * 60000).toISOString())}</span>
      </div>
      <label className="field">
        <span>What is it? (optional)</span>
        <input className="input" value={description} maxLength={300} onChange={(e) => setDescription(e.target.value)} placeholder="Rice and black beans" />
      </label>
      <label className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap", gap: "var(--s-3)", minHeight: 44 }}>
        <input type="checkbox" checked={attested} onChange={(e) => setAttested(e.target.checked)} style={{ width: 24, height: 24, marginTop: 2, flex: "none" }} />
        <span>I confirm this food was held at a safe temperature and is safe to donate.</span>
      </label>
      <button type="submit" className="btn btn-primary btn-lg" disabled={busy || !attested}>
        {busy ? "Posting" : "Post donation"}
      </button>
    </form>
  );
}

export default function RestaurantPage() {
  const user = useWorkspace("restaurant");
  const now = useServerNow();
  const { data, error, refresh } = usePoll<Rescue[]>(user ? "/rescues" : null, 3000);
  const [last, setLast] = useState<PostResult | null>(null);

  if (!user) return null;
  const active = (data ?? []).filter((r) => !["received", "cancelled", "expired", "rejected"].includes(r.status) && !r.is_draft);
  const done = (data ?? []).filter((r) => ["received", "cancelled", "expired", "rejected"].includes(r.status)).slice(0, 5);

  return (
    <Shell workspace="restaurant">
      <div className="grid-2" style={{ alignItems: "start" }}>
        <DonateForm
          onPosted={(r) => {
            setLast(r);
            refresh();
          }}
        />
        <section className="stack" aria-labelledby="tonight">
          <h2 id="tonight">Tonight</h2>
          {last ? <RescueSequence key={last.rescue.id} result={last} /> : null}
          {last ? (
            <div role="status" className={last.matching.matched ? "alert alert-good" : "alert alert-info"}>
              {last.matching.matched ? `Posted. A carrier is assigned to donation #${last.rescue.id}.` : `Posted donation #${last.rescue.id}. Looking for a carrier.`}
              {last.warnings.map((w) => (
                <div key={w}>{w}</div>
              ))}
            </div>
          ) : null}
          {error && !data ? <ErrorNote message={error} onRetry={refresh} /> : null}
          {!data && !error ? <Loading label="Loading your donations" /> : null}
          {data && active.length === 0 ? <Empty title="Nothing posted right now">Post surplus food and it shows up here with its pickup code.</Empty> : null}
          {active.length ? <RescueMap rescues={active} height={280} /> : null}
          {active.map((r) => (
            <div key={r.id} className="stack">
              <RescueCard rescue={r} now={now} />
              <details>
                <summary style={{ minHeight: 44, cursor: "pointer" }}>Why this assignment?</summary>
                <WhyThisAssignment rescue={r} />
              </details>
            </div>
          ))}
          {done.length ? (
            <details>
              <summary style={{ minHeight: 44, cursor: "pointer" }}>Recent ({done.length})</summary>
              <div className="stack">
                {done.map((r) => (
                  <RescueCard key={r.id} rescue={r} now={now} showCode={false} />
                ))}
              </div>
            </details>
          ) : null}
        </section>
      </div>
    </Shell>
  );
}
