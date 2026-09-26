"use client";
import { useEffect, useState } from "react";
import AppShell, { ErrorNote, Loading } from "@/components/AppShell";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";

const DAYS: { key: string; label: string }[] = [
  { key: "mon", label: "Mon" }, { key: "tue", label: "Tue" }, { key: "wed", label: "Wed" }, { key: "thu", label: "Thu" },
  { key: "fri", label: "Fri" }, { key: "sat", label: "Sat" }, { key: "sun", label: "Sun" },
];
const ALLERGENS = ["peanuts", "tree_nuts", "dairy", "eggs", "gluten", "soy", "fish", "shellfish", "sesame"];
const DIETARY_RULES = [
  { value: "halal_only", label: "Halal only" }, { value: "kosher_only", label: "Kosher only" },
  { value: "vegetarian_only", label: "Vegetarian only" }, { value: "vegan_only", label: "Vegan only" },
  { value: "no_pork", label: "No pork" }, { value: "no_beef", label: "No beef" },
];
const RECORD_FIELDS = [
  "date_time", "donor_name", "donor_address", "food_description", "food_category", "quantity_meals",
  "weight_lbs", "temperature_at_receipt", "condition", "received_by_name", "allergen_info", "donor_acknowledgment",
];

interface Profile { organization: { name: string }; completeness: { complete: boolean; missing: string[] } }

type DayWindow = { closed: boolean; start: string; end: string };
const emptyWeek = (): Record<string, DayWindow> =>
  Object.fromEntries(DAYS.map((d) => [d.key, { closed: false, start: "09:00", end: "17:00" }]));

export default function OrgOnboardingPage() {
  const user = useRequireRole(["org_staff", "org_manager"]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [week, setWeek] = useState(emptyWeek);
  const [cutoff, setCutoff] = useState("30");
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [instructions, setInstructions] = useState("");
  const [curbsideOk, setCurbsideOk] = useState(false);
  const [curbLocation, setCurbLocation] = useState("");

  const [acceptsHot, setAcceptsHot] = useState(false);
  const [hotMaxMinutes, setHotMaxMinutes] = useState("45");
  const [canHoldHot, setCanHoldHot] = useState(false);
  const [acceptsCold, setAcceptsCold] = useState(true);
  const [fridgeCapacity, setFridgeCapacity] = useState("100");
  const [acceptsFrozen, setAcceptsFrozen] = useState(false);
  const [freezerCapacity, setFreezerCapacity] = useState("50");
  const [acceptsShelfStable, setAcceptsShelfStable] = useState(true);
  const [dietaryRules, setDietaryRules] = useState<string[]>([]);
  const [refusedAllergens, setRefusedAllergens] = useState<string[]>([]);
  const [maxMealsPerDelivery, setMaxMealsPerDelivery] = useState("100");
  const [typicalNightlyNeed, setTypicalNightlyNeed] = useState("50");

  const [requiredFields, setRequiredFields] = useState<string[]>(["date_time", "food_description", "quantity_meals"]);
  const [reportFrequency, setReportFrequency] = useState("monthly");
  const [reportFormat, setReportFormat] = useState("csv");
  const [reportsTo, setReportsTo] = useState("");
  const [is501c3, setIs501c3] = useState(false);
  const [ein, setEin] = useState("");

  useEffect(() => {
    if (!user) return;
    api<Profile>("/orgs/me/profile").then(setProfile).catch((e) => setError((e as Error).message));
  }, [user]);

  if (!user) return null;

  function toggle(list: string[], setList: (v: string[]) => void, value: string) {
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
  }

  async function submitQ1(e: React.FormEvent) {
    e.preventDefault();
    setBusy("q1");
    setNote(null);
    try {
      const schedule = Object.fromEntries(DAYS.map((d) => [d.key, week[d.key].closed ? [] : [[week[d.key].start, week[d.key].end]]]));
      const p = await api<Profile>("/orgs/me/intake/Q1", {
        method: "PUT", body: {
          schedule, exceptions: [], cutoff_minutes: Number(cutoff), receiving_contact_name: contactName,
          receiving_contact_phone: contactPhone, receiving_instructions: instructions, curbside_ok: curbsideOk,
          curb_location: curbLocation,
        },
      });
      setProfile(p);
      setNote("Hours saved.");
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  async function submitQ2(e: React.FormEvent) {
    e.preventDefault();
    setBusy("q2");
    setNote(null);
    try {
      const p = await api<Profile>("/orgs/me/intake/Q2", {
        method: "PUT", body: {
          accepts_hot: acceptsHot, hot_max_minutes: acceptsHot ? Number(hotMaxMinutes) : null,
          can_hold_hot: acceptsHot ? canHoldHot : null, serves_immediately: "",
          accepts_cold: acceptsCold, fridge_capacity_meals: acceptsCold ? Number(fridgeCapacity) : null,
          accepts_frozen: acceptsFrozen, freezer_capacity_meals: acceptsFrozen ? Number(freezerCapacity) : null,
          accepts_shelf_stable: acceptsShelfStable, dietary_rules: dietaryRules, refused_allergens: refusedAllergens,
          max_meals_per_delivery: Number(maxMealsPerDelivery), typical_nightly_need: Number(typicalNightlyNeed),
        },
      });
      setProfile(p);
      setNote("Food handling saved.");
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  async function submitQ3(e: React.FormEvent) {
    e.preventDefault();
    setBusy("q3");
    setNote(null);
    try {
      const p = await api<Profile>("/orgs/me/intake/Q3", {
        method: "PUT", body: {
          required_fields: requiredFields, report_frequency: reportFrequency, report_format: reportFormat,
          reports_to: reportsTo, is_501c3: is501c3, ein: is501c3 ? ein : null,
        },
      });
      setProfile(p);
      setNote("Records saved.");
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  return (
    <AppShell icon="schedule" title="Onboarding" subtitle="Answer these three questions before deliveries can be routed to you.">
      <ErrorNote message={error} />
      {note && <div className="alert alert-good" role="status">{note}</div>}
      {!profile ? <Loading /> : (
        <>
          <div className={`alert ${profile.completeness.complete ? "alert-good" : "alert-info"}`}>
            {profile.completeness.complete ? "All three questions are answered. You can receive deliveries." :
              `Missing: ${profile.completeness.missing.join(", ")}`}
          </div>

          <form className="panel flex flex-col gap-4" onSubmit={submitQ1}>
            <h2>Q1 · When can you receive food?</h2>
            <div className="grid gap-2">
              {DAYS.map((d) => (
                <div key={d.key} className="grid grid-cols-[64px_1fr_auto_1fr] items-center gap-2">
                  <span className="text-sm font-semibold">{d.label}</span>
                  <input className="input" type="time" disabled={week[d.key].closed} value={week[d.key].start}
                    onChange={(e) => setWeek({ ...week, [d.key]: { ...week[d.key], start: e.target.value } })} />
                  <span className="text-ink-3">to</span>
                  <input className="input" type="time" disabled={week[d.key].closed} value={week[d.key].end}
                    onChange={(e) => setWeek({ ...week, [d.key]: { ...week[d.key], end: e.target.value } })} />
                  <label className="col-span-4 -mt-1 flex items-center gap-2 text-sm text-ink-3">
                    <input type="checkbox" checked={week[d.key].closed} onChange={(e) => setWeek({ ...week, [d.key]: { ...week[d.key], closed: e.target.checked } })} />
                    Closed
                  </label>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <label className="field"><span>Cutoff before closing (minutes)</span><input className="input num" type="number" min={0} value={cutoff} onChange={(e) => setCutoff(e.target.value)} /></label>
              <label className="flex items-center gap-2 pt-6"><input type="checkbox" checked={curbsideOk} onChange={(e) => setCurbsideOk(e.target.checked)} /> Can meet a vehicle at the curb</label>
            </div>
            <label className="field"><span>Receiving contact name</span><input className="input" required value={contactName} onChange={(e) => setContactName(e.target.value)} /></label>
            <label className="field"><span>Receiving contact phone</span><input className="input" required value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} /></label>
            <label className="field"><span>Receiving instructions</span><input className="input" required value={instructions} onChange={(e) => setInstructions(e.target.value)} /></label>
            {curbsideOk && <label className="field"><span>Curb location</span><input className="input" required value={curbLocation} onChange={(e) => setCurbLocation(e.target.value)} /></label>}
            <button className="btn btn-primary" disabled={busy === "q1"}>Save hours</button>
          </form>

          <form className="panel flex flex-col gap-4" onSubmit={submitQ2}>
            <h2>Q2 · What can you take?</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex items-center gap-2"><input type="checkbox" checked={acceptsHot} onChange={(e) => setAcceptsHot(e.target.checked)} /> Hot food</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={acceptsCold} onChange={(e) => setAcceptsCold(e.target.checked)} /> Cold food</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={acceptsFrozen} onChange={(e) => setAcceptsFrozen(e.target.checked)} /> Frozen food</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={acceptsShelfStable} onChange={(e) => setAcceptsShelfStable(e.target.checked)} /> Shelf-stable food</label>
            </div>
            {acceptsHot && (
              <div className="grid grid-cols-2 gap-4">
                <label className="field"><span>Max minutes pickup to arrival</span><input className="input num" type="number" value={hotMaxMinutes} onChange={(e) => setHotMaxMinutes(e.target.value)} /></label>
                <label className="flex items-center gap-2 pt-6"><input type="checkbox" checked={canHoldHot} onChange={(e) => setCanHoldHot(e.target.checked)} /> Can hold it hot</label>
              </div>
            )}
            {acceptsCold && <label className="field"><span>Fridge capacity (meals)</span><input className="input num" type="number" value={fridgeCapacity} onChange={(e) => setFridgeCapacity(e.target.value)} /></label>}
            {acceptsFrozen && <label className="field"><span>Freezer capacity (meals)</span><input className="input num" type="number" value={freezerCapacity} onChange={(e) => setFreezerCapacity(e.target.value)} /></label>}
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-semibold text-ink-2">Dietary rules (only what you strictly require)</legend>
              <div className="flex flex-wrap gap-2">
                {DIETARY_RULES.map((r) => (
                  <label key={r.value} className={`chip cursor-pointer ${dietaryRules.includes(r.value) ? "chip-accent" : ""}`}>
                    <input type="checkbox" className="sr-only" checked={dietaryRules.includes(r.value)} onChange={() => toggle(dietaryRules, setDietaryRules, r.value)} />
                    {r.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-semibold text-ink-2">Allergens you cannot accept</legend>
              <div className="flex flex-wrap gap-2">
                {ALLERGENS.map((a) => (
                  <label key={a} className={`chip cursor-pointer ${refusedAllergens.includes(a) ? "chip-bad" : ""}`}>
                    <input type="checkbox" className="sr-only" checked={refusedAllergens.includes(a)} onChange={() => toggle(refusedAllergens, setRefusedAllergens, a)} />
                    {a.replace("_", " ")}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="grid grid-cols-2 gap-4">
              <label className="field"><span>Max meals per delivery</span><input className="input num" type="number" value={maxMealsPerDelivery} onChange={(e) => setMaxMealsPerDelivery(e.target.value)} /></label>
              <label className="field"><span>Typical nightly need (meals)</span><input className="input num" type="number" value={typicalNightlyNeed} onChange={(e) => setTypicalNightlyNeed(e.target.value)} /></label>
            </div>
            <button className="btn btn-primary" disabled={busy === "q2"}>Save food handling</button>
          </form>

          <form className="panel flex flex-col gap-4" onSubmit={submitQ3}>
            <h2>Q3 · What records do you need?</h2>
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-semibold text-ink-2">Required fields on every delivery record</legend>
              <div className="flex flex-wrap gap-2">
                {RECORD_FIELDS.map((f) => (
                  <label key={f} className={`chip cursor-pointer ${requiredFields.includes(f) ? "chip-accent" : ""}`}>
                    <input type="checkbox" className="sr-only" checked={requiredFields.includes(f)} onChange={() => toggle(requiredFields, setRequiredFields, f)} />
                    {f.replace(/_/g, " ")}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="grid grid-cols-2 gap-4">
              <label className="field"><span>Report frequency</span>
                <select className="input" value={reportFrequency} onChange={(e) => setReportFrequency(e.target.value)}>
                  <option value="per_delivery">Per delivery</option><option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option><option value="quarterly">Quarterly</option>
                </select>
              </label>
              <label className="field"><span>Report format</span>
                <select className="input" value={reportFormat} onChange={(e) => setReportFormat(e.target.value)}>
                  <option value="csv">CSV</option><option value="pdf">PDF</option>
                </select>
              </label>
            </div>
            <label className="field"><span>Reports go to (optional)</span><input className="input" value={reportsTo} onChange={(e) => setReportsTo(e.target.value)} /></label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={is501c3} onChange={(e) => setIs501c3(e.target.checked)} /> We are a 501(c)(3)</label>
            {is501c3 && <label className="field"><span>EIN (12-3456789)</span><input className="input" required pattern="\d{2}-\d{7}" value={ein} onChange={(e) => setEin(e.target.value)} /></label>}
            <button className="btn btn-primary" disabled={busy === "q3"}>Save records</button>
          </form>
        </>
      )}
    </AppShell>
  );
}
