"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CarrierLine, activeTrip } from "@/components/RescueCard";
import { Shell } from "@/components/Shell";
import { Empty, ErrorNote, Loading } from "@/components/States";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/auth";
import { qty, relative, statusLabel, time } from "@/lib/format";
import { usePoll } from "@/lib/usePoll";
import { useServerNow } from "@/lib/useServerNow";
import type { OrgDeliveries, OrgDelivery, Stop } from "@/lib/types";

interface ReceiptForm {
  stop: Stop;
  required_fields: string[];
  prompt: string | null;
}

function ReceiptPanel({ d, onDone }: { d: OrgDelivery; onDone: () => void }) {
  const [form, setForm] = useState<ReceiptForm | null>(null);
  const [condition, setCondition] = useState<"accepted" | "partially_accepted" | "rejected">("accepted");
  const [meals, setMeals] = useState(d.stop.allocated_meals);
  const [reason, setReason] = useState("quantity");
  const [temp, setTemp] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<ReceiptForm>(`/stops/${d.stop.id}/receipt-form`).then(setForm).catch((e) => setError((e as Error).message));
  }, [d.stop.id]);

  const needs = (f: string) => form?.required_fields.includes(f) ?? false;

  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          await api(`/stops/${d.stop.id}/receipt`, {
            method: "POST",
            body: {
              condition,
              received_meals: condition === "rejected" ? 0 : meals,
              reject_reason: condition === "accepted" ? null : reason,
              temperature_f: temp === "" ? null : Number(temp),
              received_by_name: name,
            },
          });
          onDone();
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      {error ? <ErrorNote message={error} /> : null}
      {form?.prompt ? <p className="alert alert-info">{form.prompt}</p> : null}
      <div className="seg" role="group" aria-label="What did you accept?" style={{ flexWrap: "wrap" }}>
        {(
          [
            ["accepted", "Accepted all"],
            ["partially_accepted", "Accepted some"],
            ["rejected", "Rejected"],
          ] as const
        ).map(([v, l]) => (
          <button key={v} type="button" aria-pressed={condition === v} onClick={() => setCondition(v)}>
            {l}
          </button>
        ))}
      </div>
      {condition !== "rejected" ? (
        <label className="field">
          <span>Meals accepted</span>
          <input className="input" type="number" min={0} max={d.stop.allocated_meals} value={meals} onChange={(e) => setMeals(Number(e.target.value) || 0)} />
        </label>
      ) : null}
      {condition !== "accepted" ? (
        <label className="field">
          <span>Why</span>
          <select className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="quantity">Quantity</option>
            <option value="temperature">Temperature</option>
            <option value="packaging">Packaging</option>
            <option value="other">Other</option>
          </select>
        </label>
      ) : null}
      <label className="field">
        <span>Temperature at receipt, °F{needs("temperature_at_receipt") ? " (your records need this)" : " (optional)"}</span>
        <input className="input" inputMode="decimal" required={needs("temperature_at_receipt")} value={temp} onChange={(e) => setTemp(e.target.value.replace(/[^\d.-]/g, ""))} />
      </label>
      <label className="field">
        <span>Received by{needs("received_by_name") ? " (your records need this)" : " (optional)"}</span>
        <input className="input" autoComplete="name" required={needs("received_by_name")} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <button type="submit" className="btn btn-good btn-lg" disabled={busy || !form}>
        {busy ? "Saving" : "Confirm receipt"}
      </button>
    </form>
  );
}

function DeliveryCard({ d, now, onChanged }: { d: OrgDelivery; now: string | null; onChanged: () => void }) {
  const trip = activeTrip(d.rescue);
  const s = d.stop;
  return (
    <article className="panel stack" aria-label={`Delivery ${s.id}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>
          {s.allocated_meals} meals from {d.rescue.restaurant.name}
        </h3>
        <span className="chip">{statusLabel(s.status)}</span>
      </div>
      <p className="small muted">
        {qty(d.rescue.quantity, d.rescue.unit)}, {d.rescue.category.replace("_", " ")}
        {d.rescue.description ? `: ${d.rescue.description}` : ""}
        {s.eta && s.status === "pending" ? ` · arriving around ${time(s.eta)} (${relative(s.eta, now)})` : ""}
      </p>
      {trip ? (
        <p className="small">
          Carrier: <CarrierLine trip={trip} />
        </p>
      ) : null}
      {s.status === "pending" && s.dropoff_code ? (
        <div className="panel panel-tight stack" style={{ background: "var(--wash)", gap: "var(--s-1)" }}>
          <span className="eyebrow">Drop-off code: tell the driver when they arrive</span>
          <span className="code-big" data-testid="dropoff-code">
            {s.dropoff_code}
          </span>
        </div>
      ) : null}
      {s.status === "delivered" ? <ReceiptPanel d={d} onDone={onChanged} /> : null}
      {s.status === "received" || s.status === "rejected" ? (
        <p className="small">
          {s.received_meals ?? 0} of {s.allocated_meals} meals accepted{s.received_at ? ` at ${time(s.received_at)}` : ""}.
        </p>
      ) : null}
    </article>
  );
}

// "We need N meals tonight" (POST /orgs/me/need), ported from the organization dashboard in a073982.
function NeedForm() {
  const [need, setNeed] = useState("25");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ good: boolean; text: string } | null>(null);
  return (
    <form
      className="panel stack"
      aria-labelledby="need-title"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setNote(null);
        try {
          const res = await api<{ current_need: number }>("/orgs/me/need", { method: "POST", body: { meals: Number(need) } });
          setNote({ good: true, text: `Saved: ${res.current_need} meals needed tonight.` });
        } catch (err) {
          setNote({ good: false, text: (err as Error).message });
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2 id="need-title">Tonight&apos;s need</h2>
      <label className="field">
        <span>Meals needed tonight</span>
        <input className="input" type="number" min={0} max={10000} required value={need} onChange={(e) => setNeed(e.target.value)} />
      </label>
      {note ? (
        <p role="status" className={`alert ${note.good ? "alert-good" : "alert-bad"}`}>
          {note.text}
        </p>
      ) : null}
      <button type="submit" className="btn btn-primary" disabled={busy}>
        Update need
      </button>
      <p className="small muted">
        New organization? <Link href="/organization/onboarding">Answer the three onboarding questions</Link> before deliveries can be routed to you.
      </p>
    </form>
  );
}

export default function OrgPage() {
  const user = useWorkspace("org");
  const now = useServerNow();
  const { data, error, refresh } = usePoll<OrgDeliveries>(user ? "/orgs/me/deliveries" : null, 3000);
  if (!user) return null;
  return (
    <Shell workspace="org">
      {error && !data ? <ErrorNote message={error} onRetry={refresh} /> : null}
      {!data && !error ? <Loading label="Loading deliveries" /> : null}
      {data ? (
        <div className="grid-2" style={{ alignItems: "start" }}>
          <section className="stack" aria-labelledby="confirm">
            <h2 id="confirm">To confirm</h2>
            {data.to_confirm.length === 0 ? <p className="muted">Nothing waiting for your confirmation.</p> : null}
            {data.to_confirm.map((d) => (
              <DeliveryCard key={d.stop.id} d={d} now={now} onChanged={refresh} />
            ))}
            <h2 id="incoming">On the way</h2>
            {data.incoming.length === 0 ? <Empty title="No deliveries on the way">Incoming food shows up here with its drop-off code.</Empty> : null}
            {data.incoming.map((d) => (
              <DeliveryCard key={d.stop.id} d={d} now={now} onChanged={refresh} />
            ))}
          </section>
          <section className="stack" aria-labelledby="history">
            <NeedForm />
            <h2 id="history">Received</h2>
            {data.history.length === 0 ? <p className="muted">No confirmed deliveries yet.</p> : null}
            {data.history.slice(0, 10).map((d) => (
              <DeliveryCard key={d.stop.id} d={d} now={now} onChanged={refresh} />
            ))}
          </section>
        </div>
      ) : null}
    </Shell>
  );
}
