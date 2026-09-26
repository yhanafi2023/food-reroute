"""Written acknowledgments from receiving organizations (per delivery or monthly statement).

Generated after receipt for 501(c)(3) recipients only (the document states the org is one).
Signing records typed name, title, time and user; the rendered PDF is stored and its SHA-256
goes into the audit log. Signed PDFs cannot change (database trigger). Reminders at 3 and 7 days.
TEMPLATE: have a tax professional review before real use.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import audit, clock, notify, pdf
from app.models import Acknowledgment, DonationItem, Organization, Rescue, Trip, TripStop, User
from app.tax.calc import DISCLAIMER

REVIEW_NOTE = "Have a tax professional review this template before real use."
STATEMENTS = [
    "{org} is an organization described in section 501(c)(3) of the Internal Revenue Code.",
    "The donated food will be used solely for the care of the ill, the needy, or infants, and will not be transferred "
    "in exchange for money, other property, or services.",
    "To the best of our knowledge, the donated food meets the applicable requirements of the Federal Food, Drug, and "
    "Cosmetic Act.",
]


def _items_for_stops(db: Session, stops: List[TripStop]) -> List[Dict]:
    out = []
    for s in stops:
        rescue = s.trip.rescue
        share = (s.received_meals or 0) / rescue.est_meals if rescue.est_meals else 0
        for it in db.query(DonationItem).filter_by(rescue_id=rescue.id).order_by(DonationItem.id):
            qty = round(it.quantity * share, 2)
            if qty > 0:
                out.append({"date_received": clock.to_local(s.received_at).date().isoformat(), "description": it.description,
                            "quantity": qty, "unit": it.unit, "meals": round(it.estimated_meals * share, 1)})
    return out


def _content(db: Session, donor: Organization, receiver: Organization, stops: List[TripStop]) -> Dict:
    p = receiver.receiver_profile
    items = _items_for_stops(db, stops)
    return {
        "title": "Acknowledgment of donated food",
        "review_note": REVIEW_NOTE,
        "organization": {"legal_name": receiver.legal_name or receiver.name, "address": receiver.address, "ein": p.ein},
        "donor": {"name": donor.legal_name or donor.name, "address": donor.address},
        "dates_received": sorted({i["date_received"] for i in items}),
        "items": items,
        "statements": [s.format(org=receiver.legal_name or receiver.name) for s in STATEMENTS],
        "disclaimer": DISCLAIMER,
    }


def lines(ack: Acknowledgment) -> List[str]:
    c = ack.content
    out = [c["review_note"], "", f"Receiving organization: {c['organization']['legal_name']}",
           f"Address: {c['organization']['address']}", f"EIN: {c['organization']['ein']}", "",
           f"Donor: {c['donor']['name']}", f"Donor address: {c['donor']['address']}",
           f"Date(s) received: {', '.join(c['dates_received'])}", "", "Food received (accepted quantities only):"]
    out += [f"  {i['date_received']}  {i['description']}: {i['quantity']:g} {i['unit'].replace('_', ' ')} (about {i['meals']:g} meals)"
            for i in c["items"]]
    out += ["", "The organization states:"] + [f" - {s}" for s in c["statements"]] + [""]
    if ack.status == "signed":
        out += [f"Signed: {ack.signer_name}, {ack.signer_title}", f"Signed at: {ack.signed_at.isoformat()}Z (UTC)",
                f"Signer user ID: {ack.signed_by}"]
    elif ack.status == "declined":
        out += [f"Declined: {ack.declined_reason}"]
    else:
        out += ["Status: awaiting signature"]
    return out


def render(ack: Acknowledgment) -> bytes:
    title = "Acknowledgment of donated food" + (" (monthly statement)" if ack.kind == "monthly" else "")
    return pdf.render(title, lines(ack), footer=DISCLAIMER)


def _create(db: Session, kind: str, donor: Organization, receiver: Organization, stops: List[TripStop],
            start: date, end: date) -> Acknowledgment:
    ack = Acknowledgment(kind=kind, donor_org_id=donor.id, receiver_org_id=receiver.id, stop_ids=[s.id for s in stops],
                         period_start=start, period_end=end, content=_content(db, donor, receiver, stops),
                         created_at=clock.now())
    db.add(ack)
    db.flush()
    audit.log(db, "acknowledgment_created", entity="acknowledgment", stop_id=stops[0].id if len(stops) == 1 else None,
              rescue_id=stops[0].trip.rescue_id if len(stops) == 1 else None,
              details={"acknowledgment_id": ack.id, "kind": kind, "stop_ids": ack.stop_ids})
    managers = db.query(User).filter_by(organization_id=receiver.id, role="org_manager", active=True).all()
    notify.send(db, managers, "acknowledgment", "Donation acknowledgment to sign",
                f"Please review and sign the acknowledgment for food from {donor.name} ({kind.replace('_', ' ')}).",
                dedupe=f"ack:{ack.id}")
    return ack


def on_receipt(db: Session, stop: TripStop) -> Optional[Acknowledgment]:
    """Per-delivery orgs get an acknowledgment right away; monthly orgs get one statement per month (see monthly_due)."""
    p = stop.organization.receiver_profile
    if not (p and p.is_501c3) or (stop.received_meals or 0) <= 0 or p.ack_frequency != "per_delivery":
        return None
    day = clock.to_local(stop.received_at).date()
    return _create(db, "per_delivery", stop.trip.rescue.restaurant, stop.organization, [stop], day, day)


def monthly_due(db: Session) -> int:
    """On or after the 1st: one statement per donor and receiver for last month's deliveries not yet covered."""
    today = clock.to_local(clock.now()).date()
    end = today.replace(day=1) - timedelta(days=1)
    start = end.replace(day=1)
    lo, hi = clock.local_to_utc(datetime.combine(start, datetime.min.time())), clock.local_to_utc(datetime.combine(today.replace(day=1), datetime.min.time()))
    covered = {sid for a in db.query(Acknowledgment).all() for sid in (a.stop_ids or [])}
    groups: Dict[tuple, List[TripStop]] = {}
    for s in (db.query(TripStop).join(Trip, Trip.id == TripStop.trip_id)
              .filter(TripStop.status == "received", TripStop.received_meals > 0, TripStop.received_at >= lo, TripStop.received_at < hi)):
        p = s.organization.receiver_profile
        if s.id in covered or not (p and p.is_501c3 and p.ack_frequency == "monthly"):
            continue
        groups.setdefault((s.trip.rescue.restaurant_org_id, s.organization_id), []).append(s)
    for (donor_id, receiver_id), stops in groups.items():
        _create(db, "monthly", db.get(Organization, donor_id), db.get(Organization, receiver_id), stops, start, end)
    return len(groups)


def sign(db: Session, ack: Acknowledgment, user: User, name: str, title: str) -> Acknowledgment:
    if ack.status != "pending":
        raise HTTPException(409, f"This acknowledgment is already {ack.status}")
    ack.status, ack.signer_name, ack.signer_title, ack.signed_by, ack.signed_at = "signed", name, title, user.id, clock.now()
    content = render(ack)
    ack.signed_pdf_b64 = base64.b64encode(content).decode()
    ack.pdf_sha256 = hashlib.sha256(content).hexdigest()
    audit.log(db, "acknowledgment_signed", entity="acknowledgment", actor=user,
              details={"acknowledgment_id": ack.id, "signer_name": name, "signer_title": title,
                       "pdf_sha256": ack.pdf_sha256, "stop_ids": ack.stop_ids})
    return ack


def decline(db: Session, ack: Acknowledgment, user: User, reason: str) -> Acknowledgment:
    if ack.status != "pending":
        raise HTTPException(409, f"This acknowledgment is already {ack.status}")
    ack.status, ack.declined_reason, ack.signed_by, ack.signed_at = "declined", reason, user.id, clock.now()
    audit.log(db, "acknowledgment_declined", entity="acknowledgment", actor=user,
              details={"acknowledgment_id": ack.id, "reason": reason})
    return ack


def pdf_bytes(ack: Acknowledgment) -> bytes:
    return base64.b64decode(ack.signed_pdf_b64) if ack.signed_pdf_b64 else render(ack)


def send_reminders(db: Session) -> int:
    n = 0
    now = clock.now()
    for ack in db.query(Acknowledgment).filter_by(status="pending").all():
        age = (now - ack.created_at).days
        for day in (3, 7):
            if age >= day and day not in (ack.reminders_sent or []):
                managers = db.query(User).filter_by(organization_id=ack.receiver_org_id, role="org_manager", active=True).all()
                notify.send(db, managers, "acknowledgment", "Reminder: donation acknowledgment to sign",
                            f"An acknowledgment for food from {ack.content['donor']['name']} has been waiting {day} days.",
                            dedupe=f"ack-reminder:{ack.id}:{day}")
                ack.reminders_sent = sorted(set(ack.reminders_sent or []) | {day})
                n += 1
    return n


def for_stop(db: Session, stop: TripStop) -> Optional[Acknowledgment]:
    """The acknowledgment covering this delivery (per delivery or monthly), if any."""
    for a in db.query(Acknowledgment).filter_by(receiver_org_id=stop.organization_id).order_by(Acknowledgment.id.desc()):
        if stop.id in (a.stop_ids or []):
            return a
    return None


def rescue_for(ack: Acknowledgment, db: Session) -> Optional[Rescue]:
    return db.get(TripStop, ack.stop_ids[0]).trip.rescue if len(ack.stop_ids or []) == 1 else None
