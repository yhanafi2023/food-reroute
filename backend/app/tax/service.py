"""Tax records built from FoodFlow's own data: donation items, valuation, accepted quantities, lines.

Only food an organization accepted counts. A split rescue is shared across its
receiving orgs in proportion to the meals each accepted. Only recipients an admin
verified as qualified donees (501(c)(3), not a private non-operating foundation)
count toward estimates; others are listed as "not included in tax estimate".
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import audit, clock
from app.assumptions import LBS_PER_MEAL, UNIT_TO_MEALS
from app.models import (
    DonationItem, MenuItem, Organization, ReceiverProfile, Rescue, RestaurantTaxProfile, Trip, TripStop, User,
)
from app.tax import calc

MENU_TO_POST_UNIT = {"meal": "individual_meal"}


def tax_profile(db: Session, org_id: int) -> RestaurantTaxProfile:
    p = db.get(RestaurantTaxProfile, org_id)
    if p is None:
        today = clock.to_local(clock.now()).date()
        p = RestaurantTaxProfile(organization_id=org_id, tax_year_start=date(today.year, 1, 1), updated_at=clock.now())
        db.add(p)
        db.flush()
    return p


def uses_election(p: RestaurantTaxProfile) -> bool:
    return bool(p.use_25pct_basis_election and not p.keeps_inventory)


def value_from_menu(item: DonationItem, menu: MenuItem, profile: RestaurantTaxProfile) -> None:
    item.fmv_per_unit, item.fmv_method = menu.menu_price_per_unit, "own_price_same_item"
    if uses_election(profile):
        item.basis_per_unit, item.basis_method = round(0.25 * menu.menu_price_per_unit, 4), "election_25pct_fmv"
    elif menu.actual_cost_per_unit is not None:
        item.basis_per_unit, item.basis_method = menu.actual_cost_per_unit, "actual_cost"
    elif menu.food_cost_pct is not None:
        item.basis_per_unit, item.basis_method = round(menu.menu_price_per_unit * menu.food_cost_pct / 100, 4), "food_cost_pct"


def create_items(db: Session, rescue: Rescue, specs: List[Dict[str, Any]]) -> List[DonationItem]:
    """specs: [{menu_item_id?, description?, quantity, unit}] -> donation items (valued when a menu item is given)."""
    profile = tax_profile(db, rescue.restaurant_org_id)
    items = []
    for spec in specs:
        menu = db.get(MenuItem, spec["menu_item_id"]) if spec.get("menu_item_id") else None
        if menu is not None and menu.organization_id != rescue.restaurant_org_id:
            raise HTTPException(404, "Menu item not found")
        unit = menu.unit if menu else spec["unit"]
        meals_per_unit = menu.meals_per_unit if menu else UNIT_TO_MEALS[MENU_TO_POST_UNIT.get(unit, unit)]
        item = DonationItem(rescue_id=rescue.id, menu_item_id=menu.id if menu else None,
                            description=spec.get("description") or (menu.name if menu else rescue.description or
                                                                    f"{rescue.category.replace('_', '-')} food"),
                            quantity=spec["quantity"], unit=unit, estimated_meals=round(spec["quantity"] * meals_per_unit, 2),
                            weight_lbs=spec.get("weight_lbs"))
        if menu is not None:
            value_from_menu(item, menu, profile)
        db.add(item)
        items.append(item)
    db.flush()
    return items


def set_valuation(db: Session, item: DonationItem, user: User, fmv_per_unit: float, fmv_method: str,
                  basis_per_unit: Optional[float], basis_method: Optional[str]) -> DonationItem:
    profile = tax_profile(db, item.rescue.restaurant_org_id)
    if basis_method == "election_25pct_fmv" or uses_election(profile):
        if not uses_election(profile):
            raise HTTPException(422, "The 25% of FMV basis election is only available when your tax profile says you "
                                     "do not keep inventories and you chose the election")
        basis_per_unit, basis_method = round(0.25 * fmv_per_unit, 4), "election_25pct_fmv"
    elif basis_per_unit is None or basis_method is None:
        raise HTTPException(422, "Give the cost basis per unit and how you got it (actual_cost or food_cost_pct)")
    item.fmv_per_unit, item.fmv_method, item.basis_per_unit, item.basis_method = fmv_per_unit, fmv_method, basis_per_unit, basis_method
    item.valued_by, item.valued_at = user.id, clock.now()
    audit.log(db, "donation_item_valued", entity="rescue", actor=user, rescue_id=item.rescue_id,
              details={"item_id": item.id, "fmv_per_unit": fmv_per_unit, "fmv_method": fmv_method,
                       "basis_per_unit": basis_per_unit, "basis_method": basis_method})
    return item


def update_accepted(db: Session, rescue: Rescue) -> None:
    """accepted_quantity = quantity x (meals accepted across all stops / meals posted)."""
    received = sum(s.received_meals or 0 for t in db.query(Trip).filter_by(rescue_id=rescue.id) for s in t.stops
                   if s.status == "received")
    share = min(received / rescue.est_meals, 1.0) if rescue.est_meals else 0.0
    for item in db.query(DonationItem).filter_by(rescue_id=rescue.id):
        item.accepted_quantity = round(item.quantity * share, 4)


def qualified(p: Optional[ReceiverProfile]) -> bool:
    return bool(p and p.is_501c3 and p.not_private_nonoperating_foundation and p.ein_verified)


def _ack_status(db: Session, stop: TripStop) -> str:
    from app.tax.acks import for_stop
    a = for_stop(db, stop)
    if a is not None:
        return a.status
    p = stop.organization.receiver_profile
    if not (p and p.is_501c3):
        return "not applicable (recipient is not a 501(c)(3))"
    return "not yet generated (monthly statement)" if p.ack_frequency == "monthly" else "none"


def lines_for_year(db: Session, restaurant_id: int, year: int) -> List[Dict[str, Any]]:
    return lines_between(db, restaurant_id, clock.local_to_utc(datetime(year, 1, 1)), clock.local_to_utc(datetime(year + 1, 1, 1)))


def lines_between(db: Session, restaurant_id: int, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    profile = tax_profile(db, restaurant_id)
    stops = (db.query(TripStop).join(Trip, Trip.id == TripStop.trip_id).join(Rescue, Rescue.id == Trip.rescue_id)
             .filter(Rescue.restaurant_org_id == restaurant_id, TripStop.status == "received", TripStop.received_meals > 0,
                     TripStop.received_at >= start, TripStop.received_at < end)
             .order_by(TripStop.received_at).all())
    out = []
    for stop in stops:
        rescue = stop.trip.rescue
        org, p = stop.organization, stop.organization.receiver_profile
        share = stop.received_meals / rescue.est_meals if rescue.est_meals else 0
        for item in db.query(DonationItem).filter_by(rescue_id=rescue.id).order_by(DonationItem.id):
            qty = round(item.quantity * share, 4)
            if qty <= 0:
                continue
            weight = (round(item.weight_lbs * share, 2), "entered") if item.weight_lbs else \
                     (round(item.estimated_meals * share * LBS_PER_MEAL, 2), "estimated at 1.2 lbs per meal")
            line = {
                "date": clock.to_local(stop.received_at).date().isoformat(), "stop_id": stop.id, "item_id": item.id,
                "rescue_id": rescue.id, "recipient": org.legal_name or org.name, "recipient_ein": p.ein if p else None,
                "recipient_address": org.address, "description": item.description, "quantity": qty, "unit": item.unit,
                "weight_lbs": weight[0], "weight_basis": weight[1],
                "fmv_method": item.fmv_method, "basis_method": item.basis_method,
                "acknowledgment": _ack_status(db, stop), "needs_valuation": item.needs_valuation,
                "recipient_verified": qualified(p), "date_acquired": clock.to_local(rescue.prepared_at or rescue.created_at).date().isoformat(),
            }
            if item.needs_valuation:
                line.update(included=False, reason="needs valuation", fmv=None, basis=None, enhanced_deduction=None,
                            extra_benefit_vs_discarding=None, extra_benefit_note="")
            else:
                r = calc.compute_line(qty, item.fmv_per_unit, item.basis_per_unit,
                                      item.basis_method == "election_25pct_fmv", profile.keeps_inventory)
                line.update(r.as_json())
                line["included"] = qualified(p)
                line["reason"] = "" if line["included"] else "not included in tax estimate: recipient not verified"
            out.append(line)
    return out


def summary(db: Session, restaurant_id: int, year: int, lines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    profile = tax_profile(db, restaurant_id)
    lines = lines_for_year(db, restaurant_id, year) if lines is None else lines
    included = [l for l in lines if l["included"]]
    total_ded = sum((Decimal(str(l["enhanced_deduction"])) for l in included), Decimal(0))
    extras = [Decimal(str(l["extra_benefit_vs_discarding"])) for l in included if l["extra_benefit_vs_discarding"] is not None]
    extra_applies = profile.keeps_inventory and not uses_election(profile)
    # Donations exist but none can be estimated yet: say why instead of showing $0.
    no_estimate_note = ""
    if lines and not included:
        reasons = []
        if any(not l["recipient_verified"] and not l["needs_valuation"] for l in lines):
            reasons.append(calc.NOT_VERIFIED)
        if any(l["needs_valuation"] for l in lines):
            reasons.append(calc.NEEDS_VALUATION)
        no_estimate_note = " ".join(reasons)
    if no_estimate_note:
        total_extra, extra_note = None, no_estimate_note
    elif not extra_applies or (included and not extras):
        total_extra, extra_note = None, calc.ASK_PREPARER  # election, no inventory, or FMV <= basis
    else:
        total_extra, extra_note = sum(extras, Decimal(0)), ""
    total_basis = sum((Decimal(str(l["basis"])) for l in lines if l.get("basis") is not None), Decimal(0))
    per_recipient: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"lines": 0, "fmv": Decimal(0), "basis": Decimal(0),
                                                                  "enhanced_deduction": Decimal(0), "included": True})
    for l in lines:
        s = per_recipient[l["recipient"]]
        s["lines"] += 1
        s["ein"] = l["recipient_ein"]
        s["included"] = s["included"] and l["recipient_verified"]
        for k in ("fmv", "basis", "enhanced_deduction"):
            if l.get(k) is not None:
                s[k] += Decimal(str(l[k]))
    saved = calc.tax_saved(total_extra, profile.tax_rate_pct)
    unsigned = sorted({l["stop_id"] for l in lines if l["acknowledgment"] in ("pending", "none", "declined",
                                                                               "not yet generated (monthly statement)")})
    return {
        "year": year, "restaurant_id": restaurant_id,
        "profile": {"entity_type": profile.entity_type, "keeps_inventory": profile.keeps_inventory,
                    "use_25pct_basis_election": uses_election(profile), "tax_rate_pct": profile.tax_rate_pct,
                    "estimated_taxable_income": profile.estimated_taxable_income},
        "lines": lines,
        "subtotals": [{"recipient": k, "ein": v.get("ein"), "lines": v["lines"], "fmv": float(v["fmv"]),
                       "basis": float(v["basis"]), "enhanced_deduction": float(v["enhanced_deduction"]),
                       "included_in_estimate": v["included"]} for k, v in per_recipient.items()],
        "totals": {
            "enhanced_deduction": None if no_estimate_note else float(calc.money(total_ded)),
            "enhanced_deduction_display": None if no_estimate_note else calc.dollars(total_ded),
            "enhanced_deduction_note": no_estimate_note,
            "extra_benefit_vs_discarding": float(total_extra) if total_extra is not None else None,
            "extra_benefit_display": calc.dollars(total_extra) if total_extra is not None else None,
            "extra_benefit_note": extra_note,
            "estimated_tax_saved": float(saved) if saved is not None else None,
            "estimated_tax_saved_display": calc.dollars(saved) if saved is not None else None,
            "total_basis_donated": float(calc.money(total_basis)), "total_basis_display": calc.dollars(total_basis),
            "total_basis_label": "cost to remove from COGS; confirm with your preparer",
        },
        "counts": {"needs_valuation": sum(1 for l in lines if l["needs_valuation"]),
                   "unsigned_acknowledgments": len(unsigned),
                   "not_verified_recipient_lines": sum(1 for l in lines if not l["recipient_verified"])},
        "cap": calc.cap_check(total_ded, profile.estimated_taxable_income, profile.entity_type),
        "form_8283": {
            "note": "Noncash charitable contributions may require IRS Form 8283. Your preparer decides.",
            "source": "https://www.irs.gov/pub/irs-pdf/i8283.pdf",
            "fields_from_our_records": [
                {"donee_name_and_address": f"{l['recipient']}, {l['recipient_address']}", "description": l["description"],
                 "date_of_contribution": l["date"], "date_acquired": l["date_acquired"],
                 "how_acquired": "inventory prepared or purchased by the business",
                 "cost_or_adjusted_basis": l.get("basis"), "fair_market_value": l.get("fmv"),
                 "fmv_method": l["fmv_method"]} for l in lines if not l["needs_valuation"]],
        },
        "disclaimer": calc.DISCLAIMER,
    }


def dashboard(db: Session, restaurant_id: int, year: int) -> Dict[str, Any]:
    s = summary(db, restaurant_id, year)
    org = db.get(Organization, restaurant_id)
    prof = org.restaurant_profile
    start = clock.local_to_utc(datetime(year, 1, 1))
    end = clock.local_to_utc(datetime(year + 1, 1, 1))
    stops = (db.query(TripStop).join(Trip, Trip.id == TripStop.trip_id).join(Rescue, Rescue.id == Trip.rescue_id)
             .filter(Rescue.restaurant_org_id == restaurant_id, TripStop.status == "received",
                     TripStop.received_at >= start, TripStop.received_at < end).all())
    meals = sum(st.received_meals or 0 for st in stops)
    lbs = round(meals * LBS_PER_MEAL, 1)
    return {
        "restaurant": org.name, "year": year, "is_fictional": org.is_fictional,
        "headline": {"label": "Extra deduction vs. throwing it away (estimate)",
                     "value": s["totals"]["extra_benefit_display"], "note": s["totals"]["extra_benefit_note"]},
        "estimated_tax_savings": s["totals"]["estimated_tax_saved_display"],
        "estimated_tax_savings_note": ("from the tax rate you entered" if s["totals"]["estimated_tax_saved_display"] is not None
                                       else "enter your own tax rate to see estimated tax savings; FoodFlow never assumes one"),
        "enhanced_deduction_estimate": s["totals"]["enhanced_deduction_display"],
        "enhanced_deduction_note": s["totals"]["enhanced_deduction_note"],
        "meals_donated": meals, "pounds_diverted": lbs, "pounds_method": "meals x 1.2 lbs (Feeding America)",
        "unsigned_acknowledgments": s["counts"]["unsigned_acknowledgments"],
        "items_needing_valuation": s["counts"]["needs_valuation"],
        "cap_warning": s["cap"] if s["cap"] and s["cap"]["exceeds_cap"] else None,
        "avoided_disposal_cost": round(lbs * prof.hauling_cost_per_lb, 2) if prof and prof.hauling_cost_per_lb is not None else None,
        "avoided_disposal_cost_note": ("pounds diverted x your hauling cost per lb" if prof and prof.hauling_cost_per_lb is not None
                                       else "enter your own hauling cost per lb to see this; FoodFlow never assumes one"),
        "people_served_from_your_donations": sum(st.meals_served or 0 for st in stops),
        "disclaimer": calc.DISCLAIMER,
    }
