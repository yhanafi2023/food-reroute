"""Monthly "What you got back" report. Every dollar line comes from the restaurant's own entered
data or recorded history, with its formula. Lines without inputs say "Add your info to see this"."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app import pdf
from app.assumptions import LBS_PER_MEAL
from app.models import Acknowledgment, Organization, RecoveryAgreement, Rescue, Trip, TripStop
from app.tax import calc
from app.tax import service as tax
from app.value import insights
from app.value.common import to_utc

EPA_RESTAURANT_FOOD_WASTE_LBS_PER_YD3 = 396  # EPA, Volume-to-Weight Conversion Factors (April 2016), "Food Waste - restaurants"
EPA_SOURCE = "https://www.epa.gov/sites/default/files/2016-04/documents/volume_to_weight_conversion_factors_memorandum_04192016_508fnl.pdf"
DUMPSTER_NOTE_SHARE = 0.5  # ASSUMPTION: show the note when weekly diverted volume is at least half a container
LBS_SOURCE = "https://www.feedingamerica.org/ways-to-give/faq/about-our-claims"


def month_bounds(org: Organization, month: str):
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = date(y + (m == 12), (m % 12) + 1, 1)
    p = org.restaurant_profile
    return start, end, to_utc(datetime.combine(start, datetime.min.time()), p), to_utc(datetime.combine(end, datetime.min.time()), p)


def _add(link: str) -> Dict[str, Any]:
    return {"value": None, "status": "Add your info to see this", "link": link}


def _received(db: Session, org_id: int, lo: datetime, hi: datetime) -> List[TripStop]:
    return (db.query(TripStop).join(Trip, Trip.id == TripStop.trip_id).join(Rescue, Rescue.id == Trip.rescue_id)
            .filter(Rescue.restaurant_org_id == org_id, TripStop.status == "received", TripStop.received_at >= lo,
                    TripStop.received_at < hi).all())


def hauling(profile, lbs_month: float, days_in_month: int) -> Dict[str, Any]:
    if profile.hauling_cost_per_lb is None:
        line = _add("/restaurants/me/profile (hauling_cost_per_lb)")
        line["note"] = "FoodFlow never assumes a hauling cost."
    else:
        v = calc.money(Decimal(str(lbs_month)) * Decimal(str(profile.hauling_cost_per_lb)))
        line = {"value": float(v), "display": calc.dollars(v), "status": "estimated",
                "formula": f"pounds donated ({lbs_month:g}) x your hauling cost per lb (${profile.hauling_cost_per_lb:g})",
                "inputs": {"pounds_donated": lbs_month, "hauling_cost_per_lb": profile.hauling_cost_per_lb}}
    note = None
    if profile.container_size_yd3 and profile.hauling_pickups_per_week:
        weekly_yd3 = lbs_month / days_in_month * 7 / EPA_RESTAURANT_FOOD_WASTE_LBS_PER_YD3
        if weekly_yd3 >= DUMPSTER_NOTE_SHARE * profile.container_size_yd3:
            note = (f"You diverted about {weekly_yd3:.1f} cubic yards of food a week (pounds / 396 lbs per cubic yard, EPA "
                    f"restaurant food waste factor), at least half of your {profile.container_size_yd3:g} cubic yard container. "
                    "Ask your hauler whether a smaller container or fewer pickups fits.")
    line["right_size_dumpster_note"] = note
    return line


def build(db: Session, org_id: int, month: str) -> Dict[str, Any]:
    org = db.get(Organization, org_id)
    p = org.restaurant_profile
    start, end, lo, hi = month_bounds(org, month)
    stops = _received(db, org_id, lo, hi)
    meals = sum(s.received_meals or 0 for s in stops)
    lbs = round(meals * LBS_PER_MEAL, 1)

    # food cost saved from prep changes: weeks in this month after each 'tried it'
    saved_rows = [s for s in insights.savings(db, org_id, today=min(end, insights_today(org))) if s["estimated_food_cost_saved_per_week"] is not None]
    if saved_rows:
        weeks_in_month = (end - start).days / 7
        per_item = []
        total = Decimal(0)
        for s in saved_rows:
            tried = date.fromisoformat(s["tried_at"])
            weeks = max(0.0, (end - max(start, tried)).days / 7) if tried < end else 0.0
            v = calc.money(Decimal(str(s["estimated_food_cost_saved_per_week"])) * Decimal(str(round(weeks, 4))))
            total += v
            per_item.append({**s, "weeks_counted_this_month": round(weeks, 2), "value_this_month": float(v)})
        food = {"value": float(calc.money(total)), "display": calc.dollars(total), "status": "estimated",
                "formula": "(baseline surplus per week - current surplus per week) x your cost per unit x weeks since 'tried it' this month",
                "items": per_item, "weeks_in_month": round(weeks_in_month, 2), "caveat": insights.CAVEAT}
    else:
        food = _add("/restaurants/me/insights (mark a suggestion 'tried it', and add food costs to your menu items)")

    haul = hauling(p, lbs, (end - start).days)

    lines = tax.lines_between(db, org_id, lo, hi)
    s = tax.summary(db, org_id, start.year, lines=lines)
    t = s["totals"]
    if any(l["included"] for l in lines) and t["extra_benefit_vs_discarding"] is not None:
        taxline = {"extra_deduction_vs_discarding": t["extra_benefit_vs_discarding"], "display": t["extra_benefit_display"],
                   "estimated_tax_saved": t["estimated_tax_saved"], "estimated_tax_saved_display": t["estimated_tax_saved_display"],
                   "status": "estimated", "formula": "sum over accepted items: enhanced deduction - basis; tax saved = that x your tax rate",
                   "tax_rate_entered": s["profile"]["tax_rate_pct"], "disclaimer": calc.DISCLAIMER}
        if t["estimated_tax_saved"] is None:
            taxline["estimated_tax_saved_status"] = "Add your tax rate to see estimated tax saved"
    else:
        taxline = _add("/restaurants/me/menu-items and /restaurants/me/tax-profile (value your items; donations must reach a verified 501(c)(3))")

    acks = [a for a in db.query(Acknowledgment).filter_by(donor_org_id=org_id) if set(a.stop_ids or []) & {x.id for x in stops}]
    unsigned = sum(1 for a in acks if a.status != "signed")
    needs_val = s["counts"]["needs_valuation"]
    agreements = db.query(RecoveryAgreement).filter_by(restaurant_org_id=org_id).count()
    missing = []
    if unsigned:
        missing.append(f"{unsigned} unsigned acknowledgment(s)")
    if needs_val:
        missing.append(f"{needs_val} item(s) need valuation")
    if stops and not agreements:
        missing.append("no written recovery agreement uploaded")
    compliance = {"status": "records complete" if not missing else "records missing", "missing": missing}

    impact = {"meals_donated": meals, "pounds_diverted": lbs, "pounds_method": "meals x 1.2 lbs (Feeding America)",
              "pounds_source": LBS_SOURCE, "partner_organizations_served": len({x.organization_id for x in stops})}

    dollar_lines = {"food_cost_saved": food.get("value"), "avoided_hauling": haul.get("value"),
                    "estimated_tax_saved": taxline.get("estimated_tax_saved") if taxline.get("status") == "estimated" else None}
    counted = {k: v for k, v in dollar_lines.items() if v is not None}
    total = calc.money(sum((Decimal(str(v)) for v in counted.values()), Decimal(0)))
    return {
        "restaurant": org.name, "is_fictional": org.is_fictional, "month": month,
        "lines": {"food_cost_saved_from_prep_changes": food, "avoided_hauling_cost": haul,
                  "tax_extra_deduction_and_estimated_tax_saved": taxline, "compliance": compliance, "community_impact": impact},
        "estimated_total_value_this_month": {"value": float(total), "display": calc.dollars(total),
                                             "label": "estimated total value this month",
                                             "includes": list(counted), "excludes_lines_without_inputs": [k for k in dollar_lines if k not in counted],
                                             "note": "Adds only dollar lines with real inputs. The tax deduction itself is not cash; only the estimated tax saved is added."},
    }


def insights_today(org: Organization) -> date:
    from app import clock
    from app.value.common import local
    return local(clock.now(), org.restaurant_profile).date()


def render_pdf(r: Dict[str, Any]) -> bytes:
    L = r["lines"]
    def line(name, d):
        if d.get("value") is None and d.get("status") == "Add your info to see this":
            return [f"{name}: Add your info to see this ({d['link']})"]
        out = [f"{name}: ${d['display']:,} (estimated)" if d.get("display") is not None else f"{name}: -"]
        if d.get("formula"):
            out.append(f"   How: {d['formula']}")
        return out
    rows = [f"Month: {r['month']}" + (" (FICTIONAL demo data)" if r["is_fictional"] else ""), ""]
    rows += line("Food cost saved from prep changes", L["food_cost_saved_from_prep_changes"])
    for it in L["food_cost_saved_from_prep_changes"].get("items", []):
        rows.append(f"   {it['item']}: {it['baseline_per_week']:g} -> {it['current_per_week']:g} {it['unit']} per week, "
                    f"cost ${it['cost_per_unit']:g} per unit, {it['weeks_counted_this_month']:g} weeks this month")
    rows += line("Avoided hauling cost", L["avoided_hauling_cost"])
    if L["avoided_hauling_cost"].get("right_size_dumpster_note"):
        rows.append("   " + L["avoided_hauling_cost"]["right_size_dumpster_note"])
    t = L["tax_extra_deduction_and_estimated_tax_saved"]
    if t.get("status") == "estimated":
        rows.append(f"Extra tax deduction vs throwing it away: ${t['display']:,} (estimate)")
        rows.append(f"Estimated tax saved: ${t['estimated_tax_saved_display']:,}" if t["estimated_tax_saved_display"] is not None
                    else "Estimated tax saved: add your tax rate to see this")
        rows.append(f"   How: {t['formula']}")
    else:
        rows.append(f"Tax: Add your info to see this ({t['link']})")
    c = L["compliance"]
    rows.append(f"Compliance: {c['status']}" + (f" ({'; '.join(c['missing'])})" if c["missing"] else ""))
    i = L["community_impact"]
    rows.append(f"Community: {i['meals_donated']} meals, {i['pounds_diverted']:g} lbs diverted ({i['pounds_method']}), "
                f"{i['partner_organizations_served']} partner organizations")
    tot = r["estimated_total_value_this_month"]
    rows += ["", f"Estimated total value this month: ${tot['display']:,}", f"   Includes: {', '.join(tot['includes']) or 'nothing yet'}",
             f"   {tot['note']}"]
    return pdf.render(f"What you got back: {r['restaurant']}", rows, footer=calc.DISCLAIMER)

