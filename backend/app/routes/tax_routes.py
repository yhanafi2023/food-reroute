"""Tax records and estimates (IRC 170(e)(3)), qualified donee verification, acknowledgments, ROI tool.
Estimates and records for a tax preparer. Not tax advice."""
import csv
import io
import json
from datetime import date
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit, clock, pdf
from app.auth import ADMIN, ORG_MANAGER, RESTAURANT_ANY, RESTAURANT_MANAGER, get_current_user
from app.db import get_db
from app.models import (
    Acknowledgment, DonationItem, MENU_UNITS, MenuItem, ReceiverProfile, User,
)
from app.tax import acks, bmf, calc, roi, service

router = APIRouter(tags=["tax"])
STATE_INCENTIVES = Path(__file__).resolve().parents[2] / "data" / "state_incentives.json"


# ---------- tax profile ----------

class TaxProfileIn(BaseModel):
    entity_type: Literal["c_corp", "s_corp", "partnership_llc", "sole_prop", "unknown"]
    keeps_inventory: bool
    use_25pct_basis_election: bool = False
    tax_rate_pct: Optional[float] = Field(default=None, ge=0, le=100)
    estimated_taxable_income: Optional[float] = Field(default=None, ge=0)
    tax_year_start: date

    @model_validator(mode="after")
    def _election(self):
        if self.use_25pct_basis_election and self.keeps_inventory:
            raise ValueError("the 25% of FMV basis election is only for businesses not required to keep inventories")
        return self


def _profile_json(p) -> dict:
    return {k: getattr(p, k) for k in ("entity_type", "keeps_inventory", "use_25pct_basis_election", "tax_rate_pct",
                                        "estimated_taxable_income")} | {"tax_year_start": p.tax_year_start.isoformat(),
                                                                         "disclaimer": calc.DISCLAIMER}


@router.get("/restaurants/me/tax-profile")
def get_tax_profile(user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    p = service.tax_profile(db, user.organization_id)
    db.commit()
    return _profile_json(p)


@router.put("/restaurants/me/tax-profile")
def put_tax_profile(body: TaxProfileIn, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    p = service.tax_profile(db, user.organization_id)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    p.updated_at = clock.now()
    audit.log(db, "tax_profile_updated", entity="organization", actor=user, details={"organization_id": user.organization_id})
    db.commit()
    return _profile_json(p)


# ---------- menu items ----------

class MenuItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    unit: Literal["tray", "half_pan", "full_pan", "bag", "box", "meal", "lb"]
    menu_price_per_unit: float = Field(ge=0, le=10000)
    food_cost_pct: Optional[float] = Field(default=None, ge=0, le=100)
    actual_cost_per_unit: Optional[float] = Field(default=None, ge=0, le=10000)
    meals_per_unit: float = Field(gt=0, le=1000)
    category: Literal["hot", "cold", "frozen", "shelf_stable"] = "hot"
    allergens: List[str] = []
    typical_batch_size: Optional[float] = Field(default=None, gt=0, le=10000)


def menu_json(m: MenuItem) -> dict:
    return {k: getattr(m, k) for k in ("id", "name", "unit", "menu_price_per_unit", "food_cost_pct", "actual_cost_per_unit",
                                        "meals_per_unit", "category", "allergens", "typical_batch_size", "active")}


def _own_menu(db: Session, item_id: int, user: User) -> MenuItem:
    m = db.get(MenuItem, item_id)
    if m is None or m.organization_id != user.organization_id:
        raise HTTPException(404, "Menu item not found")
    return m


@router.get("/restaurants/me/menu-items")
def list_menu(user: User = Depends(RESTAURANT_ANY), db: Session = Depends(get_db)):
    items = db.query(MenuItem).filter_by(organization_id=user.organization_id, active=True).order_by(MenuItem.name).all()
    out = [menu_json(m) for m in items]
    if user.role != "restaurant_manager":
        for m in out:  # staff pick items; prices and costs are for managers
            for k in ("menu_price_per_unit", "food_cost_pct", "actual_cost_per_unit"):
                m.pop(k)
    return out


@router.post("/restaurants/me/menu-items")
def add_menu(body: MenuItemIn, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    m = MenuItem(organization_id=user.organization_id, **body.model_dump())
    db.add(m)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A menu item with this name and unit already exists")
    return menu_json(m)


@router.patch("/restaurants/me/menu-items/{item_id}")
def edit_menu(item_id: int, body: MenuItemIn, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    m = _own_menu(db, item_id, user)
    for k, v in body.model_dump().items():
        setattr(m, k, v)
    db.commit()
    return menu_json(m)


@router.delete("/restaurants/me/menu-items/{item_id}")
def delete_menu(item_id: int, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    _own_menu(db, item_id, user).active = False
    db.commit()
    return {"ok": True}


@router.post("/restaurants/me/menu-items/csv")
async def upload_menu_csv(request: Request, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    """Body: CSV text with header name,unit,menu_price_per_unit,food_cost_pct,actual_cost_per_unit,meals_per_unit,category,allergens.
    Allergens separated by ';'. Existing items with the same name and unit are updated."""
    text = (await request.body()).decode("utf-8-sig", "replace")
    created, updated, errors = 0, 0, []
    for n, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            body = MenuItemIn(name=row["name"], unit=row["unit"], menu_price_per_unit=float(row["menu_price_per_unit"]),
                              food_cost_pct=float(row["food_cost_pct"]) if row.get("food_cost_pct") else None,
                              actual_cost_per_unit=float(row["actual_cost_per_unit"]) if row.get("actual_cost_per_unit") else None,
                              meals_per_unit=float(row["meals_per_unit"]), category=row.get("category") or "hot",
                              allergens=[a.strip() for a in (row.get("allergens") or "").split(";") if a.strip()])
        except Exception as e:
            errors.append({"line": n, "error": str(e)[:200]})
            continue
        m = db.query(MenuItem).filter_by(organization_id=user.organization_id, name=body.name, unit=body.unit).one_or_none()
        if m:
            for k, v in body.model_dump().items():
                setattr(m, k, v)
            m.active = True
            updated += 1
        else:
            db.add(MenuItem(organization_id=user.organization_id, **body.model_dump()))
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "errors": errors, "units_allowed": list(MENU_UNITS)}


# ---------- donation item valuation ----------

class ValuationIn(BaseModel):
    fmv_per_unit: float = Field(ge=0, le=10000)
    fmv_method: Literal["own_price_same_item", "own_price_similar_item", "manual_entry"]
    basis_per_unit: Optional[float] = Field(default=None, ge=0, le=10000)
    basis_method: Optional[Literal["actual_cost", "food_cost_pct", "election_25pct_fmv"]] = None


@router.patch("/rescues/{rescue_id}/items/{item_id}/valuation")
def value_item(rescue_id: int, item_id: int, body: ValuationIn, user: User = Depends(RESTAURANT_MANAGER),
               db: Session = Depends(get_db)):
    item = db.get(DonationItem, item_id)
    if item is None or item.rescue_id != rescue_id or item.rescue.restaurant_org_id != user.organization_id:
        raise HTTPException(404, "Item not found")
    service.set_valuation(db, item, user, body.fmv_per_unit, body.fmv_method, body.basis_per_unit, body.basis_method)
    db.commit()
    return {"id": item.id, "needs_valuation": item.needs_valuation, "fmv_per_unit": item.fmv_per_unit,
            "fmv_method": item.fmv_method, "basis_per_unit": item.basis_per_unit, "basis_method": item.basis_method}


# ---------- reports and dashboard ----------

def _restaurant_id(user: User, restaurant_id: Optional[int]) -> int:
    if user.role == "admin":
        if restaurant_id is None:
            raise HTTPException(422, "Give restaurant_id")
        return restaurant_id
    if user.role != "restaurant_manager":
        raise HTTPException(403, "Tax records are for restaurant managers")
    return user.organization_id


def _fmt(v, dollars=True):
    if v is None:
        return ""
    return f"${calc.dollars(calc.money(v)):,}" if dollars else v


@router.get("/reports/donor-tax-summary")
def donor_tax_summary(year: int = Query(ge=2015, le=2100), format: Literal["json", "csv", "pdf"] = "json",
                      restaurant_id: Optional[int] = None, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    s = service.summary(db, _restaurant_id(user, restaurant_id), year)
    if format == "json":
        return s
    cols = ["date", "recipient", "recipient_ein", "description", "quantity", "unit", "weight_lbs", "weight_basis", "fmv",
            "fmv_method", "basis", "basis_method", "enhanced_deduction", "extra_benefit_vs_discarding", "extra_benefit_note",
            "acknowledgment", "included", "reason"]
    t = s["totals"]
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        for l in s["lines"]:
            w.writerow([l.get(c) for c in cols])
        w.writerow([])
        w.writerow(["subtotal by recipient", "ein", "lines", "fmv", "basis", "enhanced_deduction", "included_in_estimate"])
        for sub in s["subtotals"]:
            w.writerow(["", sub["ein"], sub["lines"], sub["fmv"], sub["basis"], sub["enhanced_deduction"], sub["included_in_estimate"]])
        w.writerow([])
        for k in ("enhanced_deduction", "extra_benefit_vs_discarding", "estimated_tax_saved", "total_basis_donated"):
            w.writerow([k, t[k]])
        w.writerow(["total_basis_donated_label", t["total_basis_label"]])
        w.writerow(["items_needing_valuation", s["counts"]["needs_valuation"]])
        w.writerow(["unsigned_acknowledgments", s["counts"]["unsigned_acknowledgments"]])
        w.writerow([s["form_8283"]["note"]])
        w.writerow([calc.DISCLAIMER])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="donor-tax-summary-{year}.csv"'})
    lines = [f"Year {year}. Entity type: {s['profile']['entity_type']}. Keeps inventory: {s['profile']['keeps_inventory']}.", ""]
    for l in s["lines"]:
        lines.append(f"{l['date']}  {l['recipient']} (EIN {l['recipient_ein']})  {l['description']}: {l['quantity']:g} "
                     f"{l['unit']}, {l['weight_lbs']} lbs ({l['weight_basis']})")
        if l["needs_valuation"]:
            lines.append("   NEEDS VALUATION: not included in estimates")
        else:
            extra = _fmt(l["extra_benefit_vs_discarding"]) or l["extra_benefit_note"]
            lines.append(f"   FMV {_fmt(l['fmv'])} ({l['fmv_method']})  basis {_fmt(l['basis'])} ({l['basis_method']})  "
                         f"enhanced deduction {_fmt(l['enhanced_deduction'])}  extra vs discarding: {extra}")
            if not l["included"]:
                lines.append(f"   {l['reason']}")
        lines.append(f"   Acknowledgment: {l['acknowledgment']}")
    lines += ["", "Subtotals by recipient:"] + [
        f"  {sub['recipient']} (EIN {sub['ein']}): {sub['lines']} lines, FMV {_fmt(sub['fmv'])}, basis {_fmt(sub['basis'])}, "
        f"enhanced deduction {_fmt(sub['enhanced_deduction'])}{'' if sub['included_in_estimate'] else ' (not included: recipient not verified)'}"
        for sub in s["subtotals"]]
    lines += ["", f"Estimated enhanced deduction (verified recipients): {_fmt(t['enhanced_deduction'])}",
              f"Extra deduction vs throwing it away: {_fmt(t['extra_benefit_vs_discarding']) or t['extra_benefit_note']}",
              f"Estimated tax saved: {_fmt(t['estimated_tax_saved']) or 'enter your tax rate to see this'}",
              f"Total basis of donated inventory: {_fmt(t['total_basis_donated'])} ({t['total_basis_label']})",
              f"Items needing valuation: {s['counts']['needs_valuation']}; unsigned acknowledgments: {s['counts']['unsigned_acknowledgments']}"]
    if s["cap"]:
        lines += ["", s["cap"]["note"]]
    lines += ["", s["form_8283"]["note"], "Fields Form 8283 typically asks for, from our records:"]
    for f in s["form_8283"]["fields_from_our_records"]:
        lines.append(f"  {f['date_of_contribution']} | {f['donee_name_and_address']} | {f['description']} | acquired "
                     f"{f['date_acquired']} ({f['how_acquired']}) | basis {_fmt(f['cost_or_adjusted_basis'])} | FMV "
                     f"{_fmt(f['fair_market_value'])} ({f['fmv_method']})")
    return Response(pdf.render(f"Donor tax summary {year} (estimates)", lines, footer=calc.DISCLAIMER),
                    media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="donor-tax-summary-{year}.pdf"'})


@router.get("/restaurants/me/benefits")
def my_benefits(year: Optional[int] = None, user: User = Depends(RESTAURANT_MANAGER), db: Session = Depends(get_db)):
    return service.dashboard(db, user.organization_id, year or clock.to_local(clock.now()).year)


# ---------- acknowledgments ----------

def ack_json(a: Acknowledgment) -> dict:
    return {"id": a.id, "kind": a.kind, "status": a.status, "stop_ids": a.stop_ids, "period_start": a.period_start.isoformat(),
            "period_end": a.period_end.isoformat(), "signer_name": a.signer_name, "signer_title": a.signer_title,
            "signed_at": a.signed_at.isoformat() + "Z" if a.signed_at else None, "declined_reason": a.declined_reason,
            "pdf_sha256": a.pdf_sha256, "content": a.content}


@router.get("/acknowledgments")
def list_acks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Acknowledgment)
    if user.role in ("org_staff", "org_manager"):
        q = q.filter_by(receiver_org_id=user.organization_id)
    elif user.role == "restaurant_manager":
        q = q.filter_by(donor_org_id=user.organization_id)
    elif user.role != "admin":
        raise HTTPException(403, "Acknowledgments are for restaurant managers and receiving organizations")
    return [ack_json(a) for a in q.order_by(Acknowledgment.id.desc()).limit(200)]


def _ack(db: Session, ack_id: int, user: User) -> Acknowledgment:
    a = db.get(Acknowledgment, ack_id)
    if a is None or (user.role != "admin" and user.organization_id not in (a.donor_org_id, a.receiver_org_id)):
        raise HTTPException(404, "Acknowledgment not found")
    return a


@router.get("/acknowledgments/{ack_id}")
def get_ack(ack_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ack_json(_ack(db, ack_id, user))


@router.get("/acknowledgments/{ack_id}/pdf")
def ack_pdf(ack_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return Response(acks.pdf_bytes(_ack(db, ack_id, user)), media_type="application/pdf")


class SignIn(BaseModel):
    signer_name: str = Field(min_length=2, max_length=120)
    signer_title: str = Field(min_length=2, max_length=120)


@router.post("/acknowledgments/{ack_id}/sign")
def sign_ack(ack_id: int, body: SignIn, user: User = Depends(ORG_MANAGER), db: Session = Depends(get_db)):
    a = _ack(db, ack_id, user)
    if a.receiver_org_id != user.organization_id:
        raise HTTPException(403, "Only the receiving organization signs its acknowledgment")
    acks.sign(db, a, user, body.signer_name, body.signer_title)
    db.commit()
    return ack_json(a)


@router.post("/acknowledgments/{ack_id}/decline")
def decline_ack(ack_id: int, reason: str = Body(..., embed=True, min_length=3, max_length=300),
                user: User = Depends(ORG_MANAGER), db: Session = Depends(get_db)):
    a = _ack(db, ack_id, user)
    if a.receiver_org_id != user.organization_id:
        raise HTTPException(403, "Only the receiving organization can decline its acknowledgment")
    acks.decline(db, a, user, reason)
    db.commit()
    return ack_json(a)


# ---------- qualified donee verification (admin) ----------

@router.post("/admin/eo-bmf/import")
async def import_bmf(request: Request, source: str = Query("uploaded EO BMF CSV", max_length=300),
                     user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    """Body: an EO BMF CSV (header EIN,NAME,...,SUBSECTION,...,FOUNDATION,...)."""
    n = bmf.import_csv_text(db, (await request.body()).decode("utf-8", "replace"), source)
    db.commit()
    return {"imported": n, "source": source}


@router.post("/admin/eo-bmf/fetch")
def fetch_bmf(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    """Download the configured state file (EO_BMF_URL, default Florida) from irs.gov and import it."""
    n = bmf.fetch_and_import(db)
    db.commit()
    return {"imported": n, "source": bmf.EO_BMF_URL}


def _receiver(db: Session, org_id: int) -> ReceiverProfile:
    p = db.get(ReceiverProfile, org_id)
    if p is None:
        raise HTTPException(404, "Receiving organization not found")
    return p


@router.get("/admin/orgs/{org_id}/irs-match")
def irs_match(org_id: int, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    return bmf.match(db, _receiver(db, org_id))


class VerifyIn(BaseModel):
    confirm: bool
    method: Literal["eo_bmf", "teos_manual"]
    is_501c3: Optional[bool] = None
    not_private_nonoperating_foundation: Optional[bool] = None
    note: str = Field(default="", max_length=300)


@router.post("/admin/orgs/{org_id}/verify-qualified-donee")
def verify_donee(org_id: int, body: VerifyIn, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    p = _receiver(db, org_id)
    if not body.confirm:
        p.ein_verified, p.verification_source = False, f"unverified by admin {clock.now().date().isoformat()}"
    elif body.method == "eo_bmf":
        m = bmf.match(db, p)
        if not m["found"]:
            raise HTTPException(409, m["message"])
        if not m["qualified_donee"]:
            raise HTTPException(409, f"The IRS record does not show a qualified donee: {m['checks']}")
        p.is_501c3, p.not_private_nonoperating_foundation = True, True
        p.verification_source = f"IRS EO BMF: {m['record']['source']} (EIN {m['record']['ein']}, subsection " \
                                f"{m['record']['subsection']}, foundation {m['record']['foundation']})"
        p.ein_verified = True
    else:
        if body.is_501c3 is None or body.not_private_nonoperating_foundation is None or not body.note:
            raise HTTPException(422, "For a manual check, record what the IRS search showed and a note")
        p.is_501c3, p.not_private_nonoperating_foundation = body.is_501c3, body.not_private_nonoperating_foundation
        p.verification_source = f"IRS Tax Exempt Organization Search, manual check by admin: {body.note}"
        p.ein_verified = bool(body.is_501c3 and body.not_private_nonoperating_foundation)
    p.ein_verified_by, p.ein_verified_at = user.id, clock.now()
    audit.log(db, "qualified_donee_verification", entity="organization", actor=user,
              details={"organization_id": org_id, "verified": p.ein_verified, "source": p.verification_source})
    db.commit()
    return {"organization_id": org_id, "verified": p.ein_verified, "verification_source": p.verification_source,
            "teos_url": bmf.TEOS_URL}


# ---------- public tools ----------

class RoiIn(BaseModel):
    avg_menu_price: float = Field(gt=0, le=10000)
    food_cost_pct: float = Field(ge=0, le=100)
    meals_per_week: float = Field(ge=0, le=100000)
    weeks_per_year: float = Field(ge=0, le=52)
    tax_rate_pct: Optional[float] = Field(default=None, ge=0, le=100)
    hauling_cost_per_lb: Optional[float] = Field(default=None, ge=0, le=100)
    lbs_per_meal: float = Field(default=1.2, gt=0, le=20)


@router.post("/tools/donation-roi")
def donation_roi(body: RoiIn):
    return roi.estimate(**body.model_dump())


@router.get("/tools/state-incentives")
def state_incentives():
    doc = json.loads(STATE_INCENTIVES.read_text())
    return [i for i in doc.get("incentives", []) if i.get("verified") is True and i.get("source_url")]

