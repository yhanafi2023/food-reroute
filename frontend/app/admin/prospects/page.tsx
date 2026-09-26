"use client";
import { useEffect, useMemo, useState } from "react";
import AppShell, { ErrorNote, Loading } from "@/components/AppShell";
import FlowMap from "@/components/FlowMap";
import SurplusLog from "@/components/SurplusLog";
import { api, isAbort } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import type { EvidenceStrength, Opportunities, Prospect, ProspectMeta, SurplusLogPayload } from "@/lib/types";

const EVIDENCE_CHIP: Record<EvidenceStrength, string> = {
  measured: "chip-good",
  documented_donation: "chip-good",
  marketplace_listing: "",
  none_found: "chip-warn",
};
const DISTANCES = [{ v: "", l: "Any distance" }, { v: "2", l: "Within 2 mi of FIU" }, { v: "5", l: "Within 5 mi" }, { v: "10", l: "Within 10 mi" }];

function Unknown() {
  return <span className="text-ink-3">Unknown</span>;
}

export default function ProspectsPage() {
  const user = useRequireRole("admin");
  const [meta, setMeta] = useState<ProspectMeta | null>(null);
  const [items, setItems] = useState<Prospect[] | null>(null);
  const [total, setTotal] = useState(0);
  const [opps, setOpps] = useState<Opportunities | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [neighborhood, setNeighborhood] = useState("");
  const [businessType, setBusinessType] = useState("");
  const [evidence, setEvidence] = useState<EvidenceStrength[]>([]);
  const [maxMiles, setMaxMiles] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Prospect | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!user) return;
    const ctrl = new AbortController();
    api<ProspectMeta>("/prospects/meta", { signal: ctrl.signal }).then(setMeta).catch((e) => !isAbort(e) && setError(e.message));
    return () => ctrl.abort();
  }, [user]);

  // Search: each change cancels the previous request; typing waits 250 ms before searching.
  useEffect(() => {
    if (!user) return;
    const ctrl = new AbortController();
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (neighborhood) params.set("neighborhood", neighborhood);
    if (businessType) params.set("business_type", businessType);
    evidence.forEach((e) => params.append("evidence", e));
    if (maxMiles) params.set("max_miles", maxMiles);
    const timer = setTimeout(() => {
      setLoading(true);
      Promise.all([
        api<{ items: Prospect[]; total: number }>(`/prospects?${params}`, { signal: ctrl.signal }),
        api<Opportunities>("/prospects/opportunities", { signal: ctrl.signal }),
      ])
        .then(([r, o]) => { setItems(r.items); setTotal(r.total); setOpps(o); setError(null); })
        .catch((e) => !isAbort(e) && setError(e.message))
        .finally(() => !ctrl.signal.aborted && setLoading(false));
    }, 250);
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [user, q, neighborhood, businessType, evidence, maxMiles, reloadKey]);

  useEffect(() => {
    if (!selectedId) return;
    const ctrl = new AbortController();
    api<Prospect>(`/prospects/${selectedId}`, { signal: ctrl.signal }).then(setDetail).catch((e) => !isAbort(e) && setError(e.message));
    return () => ctrl.abort();
  }, [selectedId]);

  const mapPoints = useMemo(
    () => (items ?? []).map((p) => ({ id: p.id, lat: p.lat, lng: p.lng, label: p.name, detail: `${p.business_type} · ${p.miles_from_fiu.toFixed(1)} mi from FIU` })),
    [items],
  );

  if (!user) return null;

  const toggleEvidence = (v: EvidenceStrength) =>
    setEvidence((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]));
  const clearFilters = () => { setQ(""); setNeighborhood(""); setBusinessType(""); setEvidence([]); setMaxMiles(""); };

  return (
    <AppShell title="Miami surplus prospects" subtitle="Researched businesses near FIU that may have recoverable surplus. Research only: none of these are FoodFlow partners.">
      {meta && (
        <p className="alert alert-info max-w-[90ch]">
          Checked {meta.checked} from public sources: business websites, a food-rescue organization&apos;s donor list, and
          public surplus-marketplace listings. A listing or a donor mention shows surplus activity. It does not show how
          much food a business discards. Distances are straight-line from {meta.reference_point.name}.
        </p>
      )}
      <ErrorNote message={error} onRetry={() => setReloadKey((k) => k + 1)} />

      <section className="panel flex flex-col gap-3" aria-labelledby="opp-title">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="opp-title" style={{ fontSize: "var(--t-lg)" }}>Ranked rescue opportunities</h2>
          <span className="text-sm text-ink-3">Only businesses with measured surplus are ranked</span>
        </div>
        {!opps ? <div className="skeleton h-16" aria-hidden /> : opps.ranked.length === 0 ? (
          <p className="text-ink-2">
            None yet. No researched business has published a measured surplus quantity, so there is nothing honest to rank.
            Open a business below and start its seven-day surplus log.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left">
                {["#", "Business", "Recoverable meals / week", "Pickups / week", "Meals / pickup", "Existing commitments", "Basis"].map((h) => <th key={h} className="eyebrow py-2 pr-4">{h}</th>)}
              </tr></thead>
              <tbody>
                {opps.ranked.map((o) => (
                  <tr key={o.id} className="border-t border-line align-top">
                    <td className="mono py-2 pr-4 font-bold">{o.rank}</td>
                    <td className="py-2 pr-4"><strong>{o.name}</strong>{o.is_demo && <span className="chip ml-2">demo partner</span>}{o.kind === "prospect" && <span className="chip ml-2">prospect</span>}</td>
                    <td className="num py-2 pr-4">{o.recoverable_meals_per_week}</td>
                    <td className="num py-2 pr-4">{o.pickups_per_week ?? <Unknown />}</td>
                    <td className="num py-2 pr-4">{o.meals_per_pickup ?? <Unknown />}</td>
                    <td className="py-2 pr-4">{o.existing_commitments.length ? o.existing_commitments.join(", ") : "None known"}</td>
                    <td className="py-2 text-ink-3">{o.basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {opps && <p className="text-xs text-ink-3">{opps.method}</p>}
      </section>

      <div className="panel flex flex-col gap-3" role="search" aria-label="Filter prospects">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="field md:col-span-2"><span>Search</span>
            <input className="input" type="search" placeholder="Name, street, cuisine..." value={q} onChange={(e) => setQ(e.target.value)} /></label>
          <label className="field"><span>Neighborhood</span>
            <select className="input" value={neighborhood} onChange={(e) => setNeighborhood(e.target.value)}>
              <option value="">All neighborhoods</option>
              {meta?.neighborhoods.map((n) => <option key={n}>{n}</option>)}
            </select></label>
          <label className="field"><span>Business type</span>
            <select className="input" value={businessType} onChange={(e) => setBusinessType(e.target.value)}>
              <option value="">All types</option>
              {meta?.business_types.map((n) => <option key={n}>{n}</option>)}
            </select></label>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <fieldset className="flex flex-wrap gap-2">
            <legend className="sr-only">Evidence strength</legend>
            {meta?.evidence_levels.map((ev) => (
              <label key={ev.value} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-3 text-sm ${evidence.includes(ev.value) ? "border-accent bg-wash" : "border-line"}`}>
                <input type="checkbox" checked={evidence.includes(ev.value)} onChange={() => toggleEvidence(ev.value)} />{ev.label}
              </label>
            ))}
          </fieldset>
          <select className="input" style={{ width: "auto" }} aria-label="Distance from FIU" value={maxMiles} onChange={(e) => setMaxMiles(e.target.value)}>
            {DISTANCES.map((d) => <option key={d.v} value={d.v}>{d.l}</option>)}
          </select>
          <button className="btn btn-ghost" onClick={clearFilters}>Clear filters</button>
          <span className="text-sm text-ink-3" role="status" aria-live="polite">{loading ? "Searching..." : items ? `${items.length} of ${total} shown` : ""}</span>
        </div>
      </div>

      {!items ? <Loading what="prospects" rows={2} /> : (
        <div className="grid gap-6 xl:grid-cols-[1fr_1.1fr]">
          <div className="flex min-w-0 flex-col gap-3">
            {items.length === 0 && <p className="panel text-ink-2">No prospects match these filters.</p>}
            {items.map((p) => (
              <button key={p.id} onClick={() => setSelectedId(p.id)} aria-pressed={selectedId === p.id}
                className={`panel panel-tight flex flex-col gap-2 text-left ${selectedId === p.id ? "border-accent" : ""}`} style={selectedId === p.id ? { borderColor: "var(--accent)" } : undefined}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <strong>{p.name}</strong>
                  <span className="mono num text-sm text-ink-2">{p.miles_from_fiu.toFixed(1)} mi</span>
                </div>
                <span className="text-sm text-ink-2">{p.business_type} · {p.neighborhood} · {p.address}</span>
                <div className="flex flex-wrap gap-1">
                  <span className={`chip ${EVIDENCE_CHIP[p.evidence_strength]}`}>{p.evidence_label}</span>
                  <span className="chip">Surplus quantity: {p.surplus_measurement ? "measured" : "unknown"}</span>
                  {p.log_summary && p.log_summary.days_logged > 0 && <span className="chip">Log {Math.min(p.log_summary.days_logged, 7)}/7</span>}
                </div>
              </button>
            ))}
          </div>
          <div className="flex min-w-0 flex-col gap-4">
            <FlowMap height={380} prospects={mapPoints} selectedId={selectedId} onSelect={setSelectedId}
              reference={meta ? { id: "fiu", lat: meta.reference_point.lat, lng: meta.reference_point.lng, label: "FIU" } : null}
              fitKey={`prospects-${mapPoints.length}`} />
            {detail && selectedId === detail.id ? (
              <ProspectDetail p={detail} onLog={(log) => { setDetail({ ...detail, log }); setReloadKey((k) => k + 1); }} />
            ) : (
              <p className="panel text-ink-2">Select a business to see its sources, contact details and surplus log.</p>
            )}
          </div>
        </div>
      )}
    </AppShell>
  );
}

function ProspectDetail({ p, onLog }: { p: Prospect; onLog: (log: SurplusLogPayload) => void }) {
  return (
    <article className="panel flex flex-col gap-4" aria-label={p.name}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h2 style={{ fontSize: "var(--t-lg)" }}>{p.name}</h2>
          <span className="text-ink-2">{p.business_type} · {p.neighborhood}</span>
        </div>
        <span className="chip chip-warn">Researched prospect · not enrolled</span>
      </div>

      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div><dt className="eyebrow">Address</dt><dd>{p.address}</dd>{p.address_note && <dd className="text-xs text-ink-3">{p.address_note}</dd>}</div>
        <div><dt className="eyebrow">Distance</dt><dd>{p.miles_from_fiu.toFixed(1)} mi straight-line from FIU</dd><dd className="text-xs text-ink-3">{p.geocode_source}</dd></div>
        <div><dt className="eyebrow">Phone</dt><dd>{p.contact.phone ? <a className="text-accent underline" href={`tel:${p.contact.phone.replace(/[^\d+]/g, "")}`}>{p.contact.phone}</a> : <Unknown />}</dd></div>
        <div><dt className="eyebrow">Email</dt><dd>{p.contact.email ? <a className="text-accent underline" href={`mailto:${p.contact.email}`}>{p.contact.email}</a> : <Unknown />}</dd></div>
        <div><dt className="eyebrow">Website</dt><dd className="break-all">{p.contact.website ? <a className="text-accent underline" href={p.contact.website} target="_blank" rel="noreferrer">{p.contact.website}</a> : <Unknown />}</dd></div>
        <div><dt className="eyebrow">Hours</dt><dd>{p.hours ?? <Unknown />}</dd></div>
        <div><dt className="eyebrow">Measured surplus</dt><dd>{p.surplus_measurement ? `${p.surplus_measurement.meals} meals per ${p.surplus_measurement.period}` : <><Unknown /> (no quantity published)</>}</dd></div>
        <div><dt className="eyebrow">Pickup frequency</dt><dd>{p.pickup_frequency ?? <Unknown />}</dd></div>
      </dl>

      <div className="flex flex-col gap-2">
        <span className="eyebrow">Evidence of surplus activity</span>
        {p.evidence.length === 0 ? <p className="text-sm text-ink-2">None found in public sources checked. This business is listed because it is a high-volume kitchen near FIU, not because of any waste claim.</p> : p.evidence.map((e) => (
          <div key={e.url} className="flex flex-col gap-1 rounded-lg border border-line p-3 text-sm">
            <p>{e.summary}</p>
            <span className="text-xs text-ink-3">
              <a className="text-accent underline" href={e.url} target="_blank" rel="noreferrer">{e.source_name}</a> · checked {e.checked} · {e.how}
            </span>
          </div>
        ))}
      </div>

      {p.existing_commitments.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="eyebrow">Existing donation or resale programs</span>
          {p.existing_commitments.map((c) => <p key={c.program} className="text-sm"><strong>{c.program}.</strong> {c.detail}</p>)}
        </div>
      )}

      <details className="text-sm">
        <summary className="cursor-pointer font-semibold">All sources ({p.sources.length})</summary>
        <ul className="flex flex-col gap-1 pt-2">
          {p.sources.map((s) => (
            <li key={s.url}><a className="text-accent underline" href={s.url} target="_blank" rel="noreferrer">{s.label}</a> <span className="text-ink-3">· checked {s.checked} · {s.how}</span></li>
          ))}
        </ul>
      </details>

      <hr className="divider" />
      <SurplusLog path={`/prospects/${p.id}/surplus-log`} data={p.log ?? null} onChange={onLog} canDelete
        who="Each day at closing, FoodFlow staff enter what the business reports: how much safe food was left and what happened to it." />
    </article>
  );
}
