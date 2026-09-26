"""Donor benefits (section 9) and records for receiving orgs and volunteers (section 10)."""
import csv
import io
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import audit, benefits, clock, reports
from app.auth import ORG_ANY, ORG_MANAGER, RESTAURANT_ANY, RESTAURANT_MANAGER, VOLUNTEER, get_current_user
from app.db import get_db
from app.models import Organization, OrgReport, RecoveryAgreement, User

router = APIRouter(tags=["records"])


def _csv(rows, header) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _restaurant_id(user: User, restaurant_id: Optional[int]) -> int:
    if user.role == "admin":
        if restaurant_id is None:
            raise HTTPException(422, "Give restaurant_id")
        return restaurant_id
    return user.organization_id


# ---------- 9b compliance records ----------

class AgreementIn(BaseModel):
    receiver_org_id: int
    signed_date: date
    document_url: str = Field(min_length=8, max_length=500, pattern=r"^https?://")


@router.post("/restaurants/me/agreements")
def add_agreement(body: AgreementIn, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    org = db.get(Organization, body.receiver_org_id)
    if org is None or org.kind != "receiver":
        raise HTTPException(404, "Receiving organization not found")
    a = RecoveryAgreement(restaurant_org_id=user.organization_id, receiver_org_id=org.id, signed_date=body.signed_date,
                          document_url=body.document_url, uploaded_by=user.id, created_at=clock.now())
    db.add(a)
    audit.log(db, "agreement_uploaded", entity="organization", actor=user, details={"receiver_org_id": org.id})
    db.commit()
    return {"id": a.id, "receiver_org_id": org.id, "signed_date": a.signed_date.isoformat(), "document_url": a.document_url}


@router.get("/reports/sb1383")
def sb1383(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), format: Literal["json", "csv"] = "json",
           restaurant_id: Optional[int] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ("restaurant_manager", "admin"):
        raise HTTPException(403, "Compliance reports are for restaurant managers")
    rep = benefits.sb1383_report(db, _restaurant_id(user, restaurant_id), month)
    if format == "json":
        return rep
    cols = ["organization", "address", "food_types", "pickups_in_month", "meals", "pounds_recovered", "written_agreements"]
    rows = [[r["organization"], r["address"], "; ".join(r["food_types"]), r["pickups_in_month"], r["meals"],
             r["pounds_recovered"], "; ".join(f"{a['signed_date']} {a['document_url']}" for a in r["written_agreements"]) or "none uploaded"]
            for r in rep["rows"]]
    rows += [[], [rep["note"]], [f"Guidance: {rep['guidance']}"], [f"Pounds: {rep['pounds_method']} ({rep['pounds_source']})"]]
    return Response(_csv(rows, cols), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="sb1383-{month}.csv"'})


# ---------- 9c restaurant dashboard, totes, public page ----------

@router.post("/restaurants/me/totes/returned")
def totes_returned(count: int = Body(..., embed=True, ge=1, le=500), user: User = Depends(RESTAURANT_ANY),
                   db: Session = Depends(get_db)):
    p = db.get(Organization, user.organization_id).restaurant_profile
    if count > p.totes_out:
        raise HTTPException(422, f"Only {p.totes_out} totes are out")
    p.totes_out -= count
    p.totes_on_hand += count
    audit.log(db, "totes_returned", entity="organization", actor=user, details={"count": count})
    db.commit()
    return {"totes_on_hand": p.totes_on_hand, "totes_out": p.totes_out}


@router.get("/public/partners/{slug}")
def public_partner(slug: str, db: Session = Depends(get_db)):
    org = db.query(Organization).filter_by(public_slug=slug).one_or_none()
    if org is None or not (org.restaurant_profile and org.restaurant_profile.public_partner_page):
        raise HTTPException(404, "Partner page not found")
    from app.tax.service import dashboard
    d = dashboard(db, org.id, clock.to_local(clock.now()).year)
    return {"name": org.name, "badge": "Food Rescue Partner", "year": d["year"], "meals_donated": d["meals_donated"],
            "pounds_diverted": d["pounds_diverted"], "pounds_method": d["pounds_method"], "is_fictional": org.is_fictional}


# ---------- 10 receiving org records ----------

def report_json(r: OrgReport) -> dict:
    return {"id": r.id, "period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat(),
            "format": r.format, "fields": r.fields, "rows": r.row_count, "generated_at": r.generated_at.isoformat() + "Z"}


@router.get("/orgs/me/reports")
def list_reports(user: User = Depends(ORG_MANAGER), db: Session = Depends(get_db)):
    return [report_json(r) for r in db.query(OrgReport).filter_by(organization_id=user.organization_id)
            .order_by(OrgReport.period_end.desc())]


@router.post("/orgs/me/reports")
def generate_report(start: date, end: date, format: Optional[Literal["csv", "pdf"]] = None,
                    user: User = Depends(ORG_MANAGER), db: Session = Depends(get_db)):
    if end < start:
        raise HTTPException(422, "end must be on or after start")
    r = reports.build(db, user.organization_id, start, end, format)
    db.commit()
    return report_json(r)


@router.get("/orgs/me/reports/{report_id}/download")
def download_report(report_id: int, user: User = Depends(ORG_MANAGER), db: Session = Depends(get_db)):
    r = db.get(OrgReport, report_id)
    if r is None or r.organization_id != user.organization_id:
        raise HTTPException(404, "Report not found")
    media, content = reports.report_bytes(r)
    return Response(content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="donations-{r.period_start}-{r.period_end}.{r.format}"'})


@router.get("/orgs/me/incomplete-deliveries")
def incomplete(user: User = Depends(ORG_ANY), db: Session = Depends(get_db)):
    from app.models import TripStop
    stops = db.query(TripStop).filter(TripStop.organization_id == user.organization_id).all()
    return [{"stop_id": s.id, "missing": s.incomplete_fields} for s in stops if s.incomplete_fields]


@router.get("/volunteers/me/hours")
def my_hours(format: Literal["json", "csv"] = "json", user: User = Depends(VOLUNTEER), db: Session = Depends(get_db)):
    rows = reports.volunteer_hours(db, user.id)
    total = round(sum(r["hours"] for r in rows), 2)
    if format == "json":
        return {"volunteer": user.name, "trips": rows, "total_hours": total,
                "method": "from accepting the trip to the last receipt confirmation"}
    cols = ["date", "started", "ended", "hours", "restaurant", "organizations", "meals", "trip_id"]
    return Response(_csv([[r[c] for c in cols] for r in rows] + [[], ["total_hours", total]], cols), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="volunteer-hours.csv"'})
