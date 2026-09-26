"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Disposition, LogEntry, SurplusLogPayload } from "@/lib/types";

const DISPOSITIONS: { value: Disposition; label: string }[] = [
  { value: "no_surplus", label: "No surplus today" },
  { value: "discarded", label: "Thrown away" },
  { value: "composted", label: "Composted" },
  { value: "donated", label: "Already donated" },
  { value: "sold_discounted", label: "Sold at a discount (e.g. a surplus app)" },
  { value: "staff_meal", label: "Eaten by staff" },
];
const LABEL = Object.fromEntries(DISPOSITIONS.map((d) => [d.value, d.label])) as Record<Disposition, string>;

function localDate(offsetDays = 0): string {
  const d = new Date(Date.now() - offsetDays * 86400000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const BLANK = (): LogEntry => ({
  log_date: localDate(), surplus_meals: 0, surplus_lbs: 0, safe_to_donate: true, disposition: "no_surplus",
  food_categories: "", ready_time: "", notes: "",
});

const TEMPLATE = [
  "date,surplus_meals,surplus_lbs,safe_to_donate (yes/no),what_happened (thrown away / composted / donated / sold discounted / staff meal / none),food_types,ready_time,notes",
  ...Array.from({ length: 7 }, (_, i) => `day ${i + 1},,,,,,,`),
].join("\n");

// Seven-day kitchen surplus log. `path` is the log endpoint (GET for entries, PUT to save a day).
export default function SurplusLog({ path, data, onChange, canDelete = false, who }: {
  path: string; data: SurplusLogPayload | null; onChange: (d: SurplusLogPayload) => void; canDelete?: boolean; who: string;
}) {
  const [form, setForm] = useState<LogEntry>(BLANK);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "good" | "bad"; text: string } | null>(null);
  const summary = data?.summary;

  const set = <K extends keyof LogEntry>(k: K, v: LogEntry[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const next = await api<SurplusLogPayload>(path, { method: "PUT", body: form });
      onChange(next);
      setMsg({ kind: "good", text: `Saved ${form.log_date}.` });
      setForm({ ...BLANK(), log_date: localDate(0) });
    } catch (err) {
      setMsg({ kind: "bad", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setBusy(true);
    try {
      onChange(await api<SurplusLogPayload>(`${path}/${id}`, { method: "DELETE" }));
    } catch (err) {
      setMsg({ kind: "bad", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const templateHref = `data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`;
  const pct = summary ? Math.min(100, (Math.min(summary.days_logged, summary.days_needed) / summary.days_needed) * 100) : 0;

  return (
    <section className="flex flex-col gap-4" aria-label="Seven-day surplus log">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3>Seven-day surplus log</h3>
          <a className="btn btn-ghost" href={templateHref} download="foodflow-7-day-surplus-log.csv">Download blank log (CSV)</a>
        </div>
        <p className="max-w-[70ch] text-sm text-ink-2">
          {who} After seven days the totals become a measured, self-reported baseline and the business can be ranked.
          Nothing is estimated.
        </p>
        {summary && (
          <div className="flex flex-col gap-1">
            <span className="text-sm font-semibold">{Math.min(summary.days_logged, summary.days_needed)} of {summary.days_needed} days logged</span>
            <div className={`bar ${summary.complete ? "bar-good" : ""}`} role="progressbar" aria-valuenow={summary.days_logged}
              aria-valuemin={0} aria-valuemax={summary.days_needed} aria-label="Days logged"><i style={{ width: `${pct}%` }} /></div>
          </div>
        )}
      </div>

      {summary?.complete && (
        <dl className="grid grid-cols-2 gap-4 rounded-lg p-4 md:grid-cols-4" style={{ background: "var(--good-wash)" }}>
          <div><dt className="eyebrow">Recoverable meals</dt><dd className="stat-value">{summary.recoverable_meals}</dd><dd className="text-xs text-ink-3">safe food thrown away or composted</dd></div>
          <div><dt className="eyebrow">Days with recoverable food</dt><dd className="stat-value">{summary.recoverable_days}</dd><dd className="text-xs text-ink-3">pickups needed per week</dd></div>
          <div><dt className="eyebrow">Already donated or sold</dt><dd className="stat-value">{summary.already_channeled_meals}</dd></div>
          <div><dt className="eyebrow">Period</dt><dd className="text-sm font-semibold">{summary.period_start} to {summary.period_end}</dd><dd className="text-xs text-ink-3">{summary.basis}</dd></div>
        </dl>
      )}

      <form className="panel flex flex-col gap-4" onSubmit={save} aria-label="Log a day">
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="field"><span>Date</span>
            <input className="input" type="date" required max={localDate()} value={form.log_date} onChange={(e) => set("log_date", e.target.value)} /></label>
          <label className="field"><span>Surplus meals</span>
            <input className="input num" type="number" min={0} required value={form.surplus_meals}
              onChange={(e) => { const n = Number(e.target.value); setForm((f) => ({ ...f, surplus_meals: n, disposition: n === 0 ? "no_surplus" : f.disposition === "no_surplus" ? "discarded" : f.disposition })); }} /></label>
          <label className="field"><span>Weight (lbs, if weighed)</span>
            <input className="input num" type="number" min={0} step="0.5" value={form.surplus_lbs} onChange={(e) => set("surplus_lbs", Number(e.target.value))} /></label>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="field"><span>What happened to it</span>
            <select className="input" value={form.disposition} onChange={(e) => set("disposition", e.target.value as Disposition)}>
              {DISPOSITIONS.filter((d) => (form.surplus_meals === 0 ? d.value === "no_surplus" : d.value !== "no_surplus")).map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select></label>
          <label className="field"><span>Ready for pickup around</span>
            <input className="input" type="time" value={form.ready_time} onChange={(e) => set("ready_time", e.target.value)} /></label>
        </div>
        <label className="field"><span>Food types</span>
          <input className="input" placeholder="e.g. rice, beans, pastries" value={form.food_categories} onChange={(e) => set("food_categories", e.target.value)} /></label>
        <label className="flex items-start gap-3 rounded-lg border border-line p-3">
          <input type="checkbox" className="mt-1 h-5 w-5" checked={form.safe_to_donate} onChange={(e) => set("safe_to_donate", e.target.checked)} />
          <span className="text-sm">This surplus was held at a safe temperature and would have been safe to donate.</span>
        </label>
        <label className="field"><span>Notes</span><textarea className="input" value={form.notes} onChange={(e) => set("notes", e.target.value)} /></label>
        {msg && <div className={`alert ${msg.kind === "good" ? "alert-good" : "alert-bad"}`} role="status">{msg.text}</div>}
        <button className="btn btn-primary btn-lg" disabled={busy}>{busy ? "Saving..." : "Save this day"}</button>
      </form>

      {data && data.entries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left">
              {["Date", "Meals", "Lbs", "What happened", "Safe", "Ready", ""].map((h) => <th key={h} className="eyebrow py-2 pr-4">{h}</th>)}
            </tr></thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.id} className="border-t border-line">
                  <td className="mono py-2 pr-4">{e.log_date}</td>
                  <td className="num py-2 pr-4">{e.surplus_meals}</td>
                  <td className="num py-2 pr-4">{e.surplus_lbs || "unknown"}</td>
                  <td className="py-2 pr-4">{LABEL[e.disposition]}</td>
                  <td className="py-2 pr-4">{e.safe_to_donate ? "yes" : "no"}</td>
                  <td className="py-2 pr-4">{e.ready_time || "unknown"}</td>
                  <td className="py-2">{canDelete && e.id != null && <button className="btn btn-ghost" disabled={busy} onClick={() => remove(e.id!)} aria-label={`Delete ${e.log_date}`}>Delete</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
