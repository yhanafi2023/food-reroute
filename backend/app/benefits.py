"""Donor benefits (section 9): tax documentation estimates, acknowledgments, compliance records.

ESTIMATES AND RECORDS ONLY. NOT TAX, LEGAL OR COMPLIANCE ADVICE.

Enhanced deduction for food inventory (IRC 170(e)(3)(C), made permanent by the PATH Act of 2015):
  deduction = min(basis + 0.5 x (FMV - basis), 2 x basis)
  Businesses not required to keep inventories may elect basis = 25% of FMV.
  Limited to 15% of taxable income (or of aggregate net income from the businesses that
  donated, for non-C corporations); excess carries forward up to 5 years.
Only donations received by admin-verified 501(c)(3) organizations count toward the estimate.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app import audit, clock, notify
from app.assumptions import BASIS_ELECTION_FRACTION, LBS_PER_MEAL, TAX_CARRYFORWARD_YEARS, TAX_INCOME_LIMIT_FRACTION
from app.models import Acknowledgment, Organization, RecoveryAgreement, Trip, TripStop, User

TAX_DISCLAIMER = "Estimate for your tax preparer. Not tax advice."
ACK_REVIEW_NOTE = "TEMPLATE: have a tax professional review before real use."
SB1383_NOTE = "Verify requirements with your local jurisdiction."
CALRECYCLE_GUIDANCE = "https://calrecycle.ca.gov/organics/slcp/foodrecovery/donors"
LBS_SOURCE = "https://www.feedingamerica.org/ways-to-give/faq/about-our-claims"


def enhanced_deduction(fmv: float, basis: float) -> float:
    """min(basis + half the appreciation, twice the basis). Never below zero."""
    if fmv <= 0 or basis < 0:
        return 0.0
    return round(max(min(basis + 0.5 * (fmv - basis), 2 * basis), 0.0), 2)


def line_values(stop: TripStop) -> Dict[str, Optional[float]]:
    """FMV and basis for the meals this org received, using the post's values (defaulted from the restaurant)."""
    r = stop.trip.rescue
    prof = r.restaurant.restaurant_profile
    meals = stop.received_meals or 0
    fmv_meal = r.fmv_per_meal
    if fmv_meal is None:
        return {"fmv": None, "basis": None, "deduction": None, "basis_method": "missing FMV"}
    if prof and prof.basis_election_25pct:
        basis_meal, method = BASIS_ELECTION_FRACTION * fmv_meal, "25% of FMV election"
    elif r.cost_basis_per_meal is not None:
        basis_meal, method = r.cost_basis_per_meal, "cost basis entered by restaurant"
    else:
        return {"fmv": round(fmv_meal * meals, 2), "basis": None, "deduction": None, "basis_method": "missing cost basis"}
    fmv, basis = round(fmv_meal * meals, 2), round(basis_meal * meals, 2)
    return {"fmv": fmv, "basis": basis, "deduction": enhanced_deduction(fmv, basis), "basis_method": method}


def _received_stops(db: Session, restaurant_id: int, start: datetime, end: datetime) -> List[TripStop]:
    from app.models import Rescue

    return (db.query(TripStop).join(Trip, Trip.id == TripStop.trip_id).join(Rescue, Rescue.id == Trip.rescue_id)
            .filter(Rescue.restaurant_org_id == restaurant_id, TripStop.status == "received",
                    TripStop.received_at >= start, TripStop.received_at < end).all())


def tax_summary(db: Session, restaurant_id: int, year: int) -> Dict[str, Any]:
    start = clock.local_to_utc(datetime(year, 1, 1))
    end = clock.local_to_utc(datetime(year + 1, 1, 1))
    lines, total, excluded = [], 0.0, 0
    for s in sorted(_received_stops(db, restaurant_id, start, end), key=lambda x: x.received_at):
        p = s.organization.receiver_profile
        verified = bool(p and p.is_501c3 and p.ein_verified)
        v = line_values(s)
        counts = verified and v["deduction"] is not None
        if counts:
            total += v["deduction"]
        elif not verified:
            excluded += 1
        ack = db.query(Acknowledgment).filter_by(stop_id=s.id).one_or_none()
        lines.append({
            "date": clock.to_local(s.received_at).date().isoformat(), "stop_id": s.id, "receiving_org": s.organization.name,
            "ein": p.ein if p else None, "org_verified_501c3": verified, "meals": s.received_meals,
            "lbs_est": round((s.received_meals or 0) * LBS_PER_MEAL, 1), "fmv": v["fmv"], "basis": v["basis"],
            "basis_method": v["basis_method"], "estimated_deduction": v["deduction"] if counts else 0.0,
            "counts_toward_estimate": counts,
            "note": "" if counts else ("receiving org is not an admin-verified 501(c)(3)" if not verified else v["basis_method"]),
            "acknowledgment": ack.status if ack else "none",
        })
    return {
        "year": year, "restaurant_id": restaurant_id, "lines": lines, "estimated_total_deduction": round(total, 2),
        "excluded_unverified_org_lines": excluded,
        "limits_note": (f"The enhanced deduction is limited to {int(TAX_INCOME_LIMIT_FRACTION * 100)}% of taxable income "
                        f"(or of aggregate net income from the donating businesses for non-C corporations); any excess "
                        f"carries forward up to {TAX_CARRYFORWARD_YEARS} years."),
        "formula": "min(basis + 0.5 x (FMV - basis), 2 x basis) per IRC 170(e)(3)(C); optional 25% of FMV basis election",
        "disclaimer": TAX_DISCLAIMER,
    }


def create_acknowledgment(db: Session, stop: TripStop) -> Acknowledgment:
    existing = db.query(Acknowledgment).filter_by(stop_id=stop.id).one_or_none()
    if existing:
        return existing
    r = stop.trip.rescue
    org = stop.organization
    p = org.receiver_profile
    content = {
        "title": "Acknowledgment of food donation",
        "review_note": ACK_REVIEW_NOTE,
        "donor": {"name": r.restaurant.legal_name or r.restaurant.name, "address": r.restaurant.address},
        "date_received": clock.to_local(stop.received_at).date().isoformat() if stop.received_at else None,
        "food_description": r.description or f"{r.quantity:g} {r.unit.replace('_', ' ')} of prepared food",
        "quantity_meals": stop.received_meals,
        "weight_lbs_estimated": round((stop.received_meals or 0) * LBS_PER_MEAL, 1),
        "donee": {"legal_name": org.legal_name or org.name, "ein": p.ein if p else None,
                  "is_501c3": bool(p and p.is_501c3), "ein_verified_by_admin": bool(p and p.ein_verified)},
        "statements": [
            "The donee will use the property solely for the care of the ill, the needy, or infants.",
            "The donee will not transfer the property in exchange for money, other property, or services.",
            "The property satisfies the applicable requirements of the Federal Food, Drug, and Cosmetic Act.",
        ],
        "disclaimer": TAX_DISCLAIMER,
    }
    ack = Acknowledgment(stop_id=stop.id, donor_org_id=r.restaurant_org_id, receiver_org_id=org.id, content=content,
                         created_at=clock.now())
    db.add(ack)
    db.flush()
    audit.log(db, "acknowledgment_created", entity="acknowledgment", rescue_id=r.id, stop_id=stop.id,
              details={"acknowledgment_id": ack.id})
    managers = db.query(User).filter_by(organization_id=org.id, role="org_manager", active=True).all()
    notify.send(db, managers, "acknowledgment", "Donation acknowledgment to sign",
                f"Please review and sign the acknowledgment for {stop.received_meals} meals from {r.restaurant.name}.",
                dedupe=f"ack:{ack.id}")
    return ack


def sign_acknowledgment(db: Session, ack: Acknowledgment, user: User, signer_name: str) -> Acknowledgment:
    ack.status, ack.signer_name, ack.signed_by, ack.signed_at = "signed", signer_name, user.id, clock.now()
    audit.log(db, "acknowledgment_signed", entity="acknowledgment", actor=user, stop_id=ack.stop_id,
              details={"acknowledgment_id": ack.id, "signer_name": signer_name})
    return ack


def acknowledgment_lines(ack: Acknowledgment) -> List[str]:
    c = ack.content
    return [c["review_note"], "", f"Donor: {c['donor']['name']}", f"Donor address: {c['donor']['address']}",
            f"Date received: {c['date_received']}", f"Food: {c['food_description']}",
            f"Quantity: {c['quantity_meals']} meals (about {c['weight_lbs_estimated']} lbs at 1.2 lbs/meal)",
            f"Donee: {c['donee']['legal_name']}", f"Donee EIN: {c['donee']['ein'] or 'not provided'}", "",
            "The donee states:"] + [f" - {s}" for s in c["statements"]] + [
            "", f"Status: {ack.status}" + (f", signed by {ack.signer_name} on {ack.signed_at.date().isoformat()}" if ack.signed_at else ""),
            "", c["disclaimer"]]


def sb1383_report(db: Session, restaurant_id: int, month: str) -> Dict[str, Any]:
    """California SB 1383 edible food recovery records for one month (first jurisdiction template)."""
    y, m = map(int, month.split("-"))
    start = clock.local_to_utc(datetime(y, m, 1))
    end = clock.local_to_utc(datetime(y + (m == 12), (m % 12) + 1, 1))
    per_org: Dict[int, Dict[str, Any]] = {}
    for s in _received_stops(db, restaurant_id, start, end):
        org = s.organization
        e = per_org.setdefault(org.id, {"organization": org.name, "address": org.address, "food_types": set(),
                                        "pickups": set(), "meals": 0, "pounds_recovered": 0.0})
        e["food_types"].add(s.trip.rescue.description or "prepared food")
        e["pickups"].add(s.trip_id)
        e["meals"] += s.received_meals or 0
        e["pounds_recovered"] += (s.received_meals or 0) * LBS_PER_MEAL
    agreements = db.query(RecoveryAgreement).filter_by(restaurant_org_id=restaurant_id).all()
    rows = []
    for oid, e in per_org.items():
        rows.append({"organization": e["organization"], "address": e["address"], "food_types": sorted(e["food_types"]),
                     "pickups_in_month": len(e["pickups"]), "meals": e["meals"],
                     "pounds_recovered": round(e["pounds_recovered"], 1),
                     "written_agreements": [{"signed_date": a.signed_date.isoformat(), "document_url": a.document_url}
                                            for a in agreements if a.receiver_org_id == oid]})
    return {"template": "California SB 1383 edible food recovery (commercial edible food generator records)",
            "month": month, "rows": rows,
            "record_items": ["contract or written agreement information", "schedules for donation deliveries or collections",
                             "pounds donated per month for each food recovery organization", "types of food each organization receives"],
            "pounds_method": "meals x 1.2 lbs (Feeding America)", "pounds_source": LBS_SOURCE,
            "guidance": CALRECYCLE_GUIDANCE, "note": SB1383_NOTE}


def restaurant_dashboard(db: Session, restaurant_id: int, year: int) -> Dict[str, Any]:
    org = db.get(Organization, restaurant_id)
    prof = org.restaurant_profile
    start = clock.local_to_utc(datetime(year, 1, 1))
    end = clock.local_to_utc(datetime(year + 1, 1, 1))
    stops = _received_stops(db, restaurant_id, start, end)
    meals = sum(s.received_meals or 0 for s in stops)
    lbs = round(meals * LBS_PER_MEAL, 1)
    acks = db.query(Acknowledgment).filter_by(donor_org_id=restaurant_id).all()
    served = sum(s.meals_served or 0 for s in stops)
    tax = tax_summary(db, restaurant_id, year)
    return {
        "restaurant": org.name, "year": year, "meals_donated": meals, "pounds_diverted": lbs,
        "pounds_method": "meals x 1.2 lbs", "pounds_source": LBS_SOURCE,
        "estimated_deduction": tax["estimated_total_deduction"], "tax_disclaimer": TAX_DISCLAIMER,
        "acknowledgments": {"signed": sum(a.status == "signed" for a in acks),
                            "pending_signature": sum(a.status == "pending_signature" for a in acks)},
        "avoided_disposal_cost": round(lbs * prof.hauling_cost_per_lb, 2) if prof and prof.hauling_cost_per_lb is not None else None,
        "avoided_disposal_cost_note": ("pounds diverted x your hauling cost per lb" if prof and prof.hauling_cost_per_lb is not None
                                       else "enter your own hauling cost per lb to see this; FoodFlow never assumes one"),
        "people_served_from_your_donations": served,
        "people_served_note": "meals the receiving organizations recorded as served (anonymized)",
        "public_partner_page": bool(prof and prof.public_partner_page),
    }

