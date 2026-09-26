"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import AppShell, { ErrorNote, LiveStatus, Loading, Stat } from "@/components/AppShell";
import FlowMap, { type MapRoute, type Mover } from "@/components/FlowMap";
import WhyThisMatch from "@/components/WhyThisMatch";
import { api, isAbort } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { clock, minutesUntil, number, until, usd } from "@/lib/format";
import type { EtaInfo, Forecast, Match, Network, SimEvent, Simulation } from "@/lib/types";
import { usePoll } from "@/lib/usePoll";

interface SimState {
  running: boolean;
  stopped: boolean;
  clock: string;
  movers: Mover[];
  routes: MapRoute[];
  posted: { id: number; name: string; lat: number; lng: number }[];
  feed: { key: string; clock: string; text: string }[];
  totals: { meals_rescued: number; lbs_diverted: number; deliveries_completed: number };
  done: boolean;
}

const EMPTY_SIM: SimState = {
  running: false, stopped: false, clock: "", movers: [], routes: [], posted: [], feed: [], done: false,
  totals: { meals_rescued: 0, lbs_diverted: 0, deliveries_completed: 0 },
};

function describe(e: SimEvent): string {
  switch (e.type) {
    case "rescue_posted": return `${e.rescue.restaurant_name} posts ${e.rescue.meals} meals`;
    case "matched": return `${e.driver.name} matched: ${e.stops.map((s) => `${s.meals} to ${s.name}`).join(", ")}`;
    case "delivered": return `Delivered ${e.meals} meals in ${Math.round(e.minutes)} min`;
    case "unmatched": return `Rescue ${e.rescue_id} waiting: ${e.reason}`;
  }
}

function CountUp({ value, format = number }: { value: number; format?: (n: number) => string }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current;
    if (start === value) return;
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      const f = Math.min((t - t0) / 700, 1);
      const v = start + (value - start) * (1 - Math.pow(1 - f, 3));
      from.current = v;
      setShown(v);
      if (f < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className="num">{format(Math.round(shown))}</span>;
}

function applyEvents(s: SimState, due: SimEvent[]): SimState {
  const st = { ...s };
  for (const e of due) {
    st.clock = e.clock;
    st.feed = [{ key: `${e.type}-${e.t_ms}-${"rescue_id" in e ? e.rescue_id : e.rescue.id}`, clock: e.clock, text: describe(e) }, ...st.feed].slice(0, 7);
    if (e.type === "rescue_posted") st.posted = [...st.posted, { id: e.rescue.id, name: e.rescue.restaurant_name, lat: e.rescue.lat, lng: e.rescue.lng }];
    if (e.type === "matched") {
      st.routes = [...st.routes, { id: `sim${e.rescue_id}`, geometry: e.route.geometry, stops: e.stops.map((x) => ({ lat: x.lat, lng: x.lng, label: x.name })) }];
      st.movers = [
        ...st.movers.filter((m) => m.id !== `sim-d${e.driver.id}-idle`),
        { id: `sim-d${e.driver.id}-${e.rescue_id}`, name: e.driver.name, path: e.route.geometry, startedAt: performance.now(), durationMs: e.duration_ms },
      ];
    }
    if (e.type === "delivered") {
      st.totals = e.impact;
      st.routes = st.routes.filter((r) => r.id !== `sim${e.rescue_id}`);
      st.posted = st.posted.filter((p) => p.id !== e.rescue_id);
      // the driver waits at the last drop off until the next match
      const finished = st.movers.find((m) => m.id === `sim-d${e.driver_id}-${e.rescue_id}`);
      st.movers = st.movers.filter((m) => m !== finished);
      if (finished) st.movers = [...st.movers, { ...finished, id: `sim-d${e.driver_id}-idle`, path: [finished.path[finished.path.length - 1]], durationMs: 1 }];
    }
  }
  return st;
}

export default function AdminDashboardPage() {
  const user = useRequireRole("ADMIN");
  const { data, error, refresh, updatedAt } = usePoll<Network>(user ? "/admin/network" : null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [eta, setEta] = useState<EtaInfo | null>(null);
  const runRef = useRef<Simulation | null>(null);
  const fetchRef = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ kind: "good" | "bad"; text: string } | null>(null);
  const [lastMatch, setLastMatch] = useState<Match | null>(null);
  const [sim, setSim] = useState<SimState>(EMPTY_SIM);
  const rafRef = useRef(0);

  useEffect(() => {
    if (!user) return;
    const ctrl = new AbortController();
    api<Forecast>("/ml/forecast", { signal: ctrl.signal }).then(setForecast).catch(() => undefined);
    api<EtaInfo>("/ml/eta", { signal: ctrl.signal }).then(setEta).catch(() => undefined);
    return () => ctrl.abort();
  }, [user]);

  useEffect(() => () => {
    cancelAnimationFrame(rafRef.current);
    fetchRef.current?.abort();
  }, []);

  const liveLayer = useMemo(() => {
    if (!data) return null;
    return {
      restaurants: data.restaurants.map((r) => ({ id: `r${r.id}`, lat: r.lat, lng: r.lng, label: r.name, detail: `${r.food_category}, ${r.seats} seats` })),
      organizations: data.organizations.map((o) => {
        const need = data.needs.find((n) => n.organization_id === o.id);
        return { id: `o${o.id}`, lat: o.lat, lng: o.lng, label: o.name, detail: need ? `Needs ${need.meals_needed - need.meals_fulfilled} meals (${need.priority})` : o.org_type };
      }),
      drivers: data.drivers.map((d) => ({ id: `d${d.id}`, lat: d.lat, lng: d.lng, label: d.name, detail: d.is_available ? "Available" : "On a delivery" })),
      routes: data.deliveries.map((d) => ({ id: `del${d.id}`, geometry: d.route.geometry, stops: d.stops.map((s) => ({ lat: s.lat, lng: s.lng, label: s.name })) })),
    };
  }, [data]);

  if (!user) return null;

  async function act<T>(name: string, fn: () => Promise<T>, success: (r: T) => string) {
    setBusy(name);
    setNote(null);
    try {
      const r = await fn();
      setNote({ kind: "good", text: success(r) });
      await refresh();
    } catch (e) {
      setNote({ kind: "bad", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function simulate() {
    cancelAnimationFrame(rafRef.current);
    fetchRef.current?.abort();
    const ctrl = new AbortController();
    fetchRef.current = ctrl;
    setBusy("sim");
    setNote(null);
    try {
      const run = await api<Simulation>("/simulation/run", { method: "POST", signal: ctrl.signal });
      runRef.current = run;
      play(run);
    } catch (e) {
      if (!isAbort(e)) setNote({ kind: "bad", text: (e as Error).message });
    } finally {
      if (fetchRef.current === ctrl) fetchRef.current = null;
      setBusy(null);
    }
  }

  function stopSimulation() {
    cancelAnimationFrame(rafRef.current);
    fetchRef.current?.abort();
    setSim((s) => ({ ...s, running: false, stopped: true }));
  }

  function restartSimulation() {
    if (runRef.current) play(runRef.current);
    else simulate();
  }

  function play(run: Simulation) {
    cancelAnimationFrame(rafRef.current);
    setSim({ ...EMPTY_SIM, running: true, clock: run.start_clock });
    let elapsed = 0;
    let last = performance.now();
    let next = 0;
    const events = run.events;
    // Elapsed time with a capped per-frame delta so a hidden tab resumes instead of jumping to the end.
    const frame = (now: number) => {
      elapsed += Math.min(now - last, 100);
      last = now;
      const due: SimEvent[] = [];
      while (next < events.length && events[next].t_ms <= elapsed) due.push(events[next++]);
      if (due.length) setSim((s) => applyEvents(s, due));
      if (elapsed < run.duration_ms) rafRef.current = requestAnimationFrame(frame);
      else setSim((s) => ({ ...s, running: false, done: true, clock: run.end_clock }));
    };
    rafRef.current = requestAnimationFrame(frame);
  }

  const simActive = sim.running || sim.done || sim.stopped;
  const impact = data?.impact;

  return (
    <AppShell
      title="Network"
      subtitle="Every restaurant, driver and organization, live."
      actions={
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-ghost" disabled={!!busy}
            onClick={() => act("match", () => api<{ matched: number; matches: Match[] }>("/matching/run", { method: "POST" }), (r) => {
              setLastMatch(r.matches[0] ?? null);
              return r.matched ? `Matched ${r.matched} open rescue${r.matched > 1 ? "s" : ""}.` : "No open rescues could be matched right now.";
            })}>
            {busy === "match" ? "Matching..." : "Run Matching"}
          </button>
          {sim.running ? (
            <button className="btn btn-primary" onClick={stopSimulation}>Stop simulation</button>
          ) : sim.stopped || sim.done ? (
            <button className="btn btn-primary" disabled={!!busy} onClick={restartSimulation}>Restart simulation</button>
          ) : (
            <button className="btn btn-primary" disabled={!!busy} onClick={simulate}>{busy === "sim" ? "Loading..." : "Simulate Tonight"}</button>
          )}
          <button className="btn btn-danger" disabled={!!busy}
            onClick={() => act("reset", () => api("/demo/reset", { method: "POST" }), () => {
              setLastMatch(null);
              setSim(EMPTY_SIM);
              return "Demo data restored.";
            })}>
            {busy === "reset" ? "Resetting..." : "Reset Demo"}
          </button>
        </div>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <LiveStatus updatedAt={updatedAt} error={error} />
        <span className="text-sm text-ink-3">Restaurants, drivers and organizations on this map are fictional demo accounts. Researched Miami businesses are on the <a className="font-semibold text-accent underline" href="/admin/prospects">Prospects</a> page.</span>
      </div>
      <ErrorNote message={error} onRetry={refresh} stale={!!data} />
      {note && <div className={`alert ${note.kind === "good" ? "alert-good" : "alert-bad"}`} role="status">{note.text}</div>}
      {!data || !liveLayer ? <Loading what="network" /> : (
        <>
          {simActive ? (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-live="polite">
              <Stat label="Simulated clock" value={<span className="mono">{sim.clock}</span>} note="Simulated data, 6 PM to 10 PM in 60 s" />
              <Stat label="Meals rescued" value={<CountUp value={sim.totals.meals_rescued} />} note="Simulated" />
              <Stat label="Lbs diverted" value={<CountUp value={sim.totals.lbs_diverted} />} note="Simulated" />
              <Stat label="Deliveries" value={<CountUp value={sim.totals.deliveries_completed} />} note="Simulated" />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat label="Open rescues" value={data.stats.open_rescues} />
              <Stat label="Active deliveries" value={data.stats.active_deliveries} />
              <Stat label="Available drivers" value={`${data.stats.available_drivers} / ${data.drivers.length}`} />
              <Stat label="Meals rescued" value={<CountUp value={impact!.meals_rescued} />} note={impact!.includes_demo_data ? "Includes demo data" : undefined} />
            </div>
          )}

          <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
            <FlowMap
              height={520}
              restaurants={liveLayer.restaurants}
              organizations={liveLayer.organizations}
              drivers={simActive ? [] : liveLayer.drivers}
              routes={simActive ? sim.routes : liveLayer.routes}
              movers={simActive ? sim.movers : []}
              chips={simActive ? [`SIMULATED · ${sim.clock}`, `${sim.routes.length} routes active`] : [`${data.deliveries.length} active routes`]}
              fitKey="network"
            />
            <aside className="flex flex-col gap-4">
              {simActive ? (
                <section className="panel flex flex-col gap-3" aria-live="polite">
                  <div className="flex items-center justify-between"><h3>Tonight</h3><span className="chip">simulated</span></div>
                  <ol className="flex flex-col gap-2 text-sm">
                    {sim.feed.map((f) => (
                      <li key={f.key} className="grid grid-cols-[64px_1fr] gap-2"><span className="mono text-ink-3">{f.clock}</span><span>{f.text}</span></li>
                    ))}
                  </ol>
                  {sim.stopped && <p className="text-sm text-ink-2">Stopped at {sim.clock}. Restart replays the same run from 6 PM.</p>}
                  {(sim.done || sim.stopped) && <button className="btn btn-ghost" onClick={() => setSim(EMPTY_SIM)}>Back to live network</button>}
                </section>
              ) : (
                <section className="panel flex flex-col gap-3">
                  <h3>Open and active rescues</h3>
                  {data.rescues.length === 0 && <p className="text-ink-3">None right now.</p>}
                  {data.rescues.map((r) => (
                    <div key={r.rescue.id} className="flex flex-col gap-1 border-b border-line pb-2 last:border-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <strong className="text-sm">{r.rescue.meals} meals · {r.rescue.restaurant_name}</strong>
                        <span className="chip">{r.rescue.status}</span>
                      </div>
                      <span className={`text-sm ${minutesUntil(r.rescue.pickup_deadline) < 30 ? "font-semibold text-warn" : "text-ink-3"}`}>
                        Pickup by {clock(r.rescue.pickup_deadline)} ({until(r.rescue.pickup_deadline)}){r.match ? ` · ${r.match.driver.name}` : ""}
                      </span>
                    </div>
                  ))}
                </section>
              )}
              <section className="panel flex flex-col gap-2">
                <span className="eyebrow">Impact so far</span>
                <span><strong className="num">{number(impact!.meals_rescued)}</strong> meals · <strong className="num">{number(impact!.lbs_diverted)}</strong> lbs · <strong className="num">{impact!.deliveries_completed}</strong> deliveries</span>
                <span className="text-sm text-ink-3">Community value estimate {usd(impact!.community_value_estimate_usd)} (assumed value per meal).{impact!.includes_demo_data ? " Includes demo data." : ""}</span>
              </section>
            </aside>
          </div>

          {lastMatch && <WhyThisMatch candidates={lastMatch.top_candidates} reasons={lastMatch.reasons} />}

          <div className="grid gap-6 lg:grid-cols-2">
            <EtaPanel info={eta} onRetrained={setEta} />
            <section className="panel flex flex-col gap-3" aria-labelledby="forecast-title">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 id="forecast-title">Surplus forecast</h3>
                <span className="chip chip-warn">Needs real data</span>
              </div>
              {!forecast ? <span className="text-ink-3">Loading...</span> : (
                <>
                  <p className="text-sm text-ink-2">{forecast.reason}</p>
                  <div className="flex flex-col gap-1">
                    <span className="text-sm font-semibold">{forecast.logged_days ?? 0} of {forecast.needed_days} real logged days</span>
                    <div className="bar" role="progressbar" aria-valuenow={forecast.logged_days ?? 0} aria-valuemin={0} aria-valuemax={forecast.needed_days}
                      aria-label="Real surplus days logged"><i style={{ width: `${Math.min(100, ((forecast.logged_days ?? 0) / (forecast.needed_days || 1)) * 100)}%` }} /></div>
                  </div>
                </>
              )}
            </section>
          </div>
        </>
      )}
    </AppShell>
  );
}

function EtaPanel({ info, onRetrained }: { info: EtaInfo | null; onRetrained: (i: EtaInfo) => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  if (!info) return <div className="skeleton h-64" aria-hidden />;
  const m = info.metrics;
  async function retrain() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<{ real_trips_used: number }>("/ml/eta/retrain", { method: "POST" });
      setMsg(`Retrained with ${r.real_trips_used} real trip legs.`);
      onRetrained(await api<EtaInfo>("/ml/eta"));
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const rows: [string, number][] = [
    ["Old rule (22 mph)", m.mae_minutes.rule_22mph],
    ["Ridge regression", m.mae_minutes.ridge],
    ["Gradient boosting (used)", m.mae_minutes.hist_gradient_boosting],
  ];
  const worst = Math.max(...rows.map((r) => r[1]));
  return (
    <section className="panel flex flex-col gap-3" aria-labelledby="eta-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="eta-title">Driver ETA model</h3>
        <span className="chip chip-good">Real road-network data</span>
      </div>
      <p className="text-sm text-ink-2">
        Trained on {info.data.pairs?.toLocaleString("en-US")} real driving times between Miami-Dade points from {info.data.source}
        {" "}({info.data.map_data}), fetched {info.data.fetched}. Average error on held-out places, lower is better:
      </p>
      <div className="grid gap-1" role="table" aria-label="Average ETA error by model">
        {rows.map(([label, v]) => (
          <div key={label} role="row" className="grid grid-cols-[170px_1fr_64px] items-center gap-2 text-sm">
            <span role="rowheader">{label}</span>
            <span role="cell" className="bar" aria-hidden><i style={{ width: `${(v / worst) * 100}%` }} /></span>
            <span role="cell" className="mono num text-right">{v.toFixed(1)} min</span>
          </div>
        ))}
      </div>
      <p className="text-sm text-ink-2">
        The likely range (P10 to P90) held {Math.round(m.p10_p90_coverage * 100)}% of held-out trips after calibration
        ({Math.round(m.p10_p90_coverage_before_calibration * 100)}% before). {info.assumptions.join(" ")}.
      </p>
      <p className="text-xs text-ink-3">{info.data.limitations} Real FoodFlow trips logged: {info.logged_legs} ({info.usable_real_legs} usable).
        {info.real_leg_mae_minutes != null ? ` Error on real trips: ${info.real_leg_mae_minutes} min.` : ""}</p>
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-ghost" disabled={busy || info.usable_real_legs === 0} onClick={retrain}>
          {busy ? "Retraining..." : "Retrain with real trips"}
        </button>
        {msg && <span className="text-sm text-ink-2" role="status">{msg}</span>}
      </div>
    </section>
  );
}
