"""Tax deduction module: calculations, accepted quantities, verification, acknowledgments, reports, ROI."""
import csv
import hashlib
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import clock
from app.db import SessionLocal, engine
from app.jobs import run_jobs
from app.main import app
from app.models import Acknowledgment, AuditEvent, Organization
from app.seed import ORGS, reset_database
from app.tax import calc
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


# ---------- pure calculations ----------

def test_fmv_at_or_below_basis_gives_fmv_and_no_extra_benefit():
    r = calc.compute_line(1, fmv_per_unit=4, basis_per_unit=5, use_election=False, keeps_inventory=True)
    assert r.enhanced_deduction == Decimal("4.00") and r.extra_benefit_vs_discarding is None
    assert r.extra_benefit_note == calc.ASK_PREPARER
    assert calc.compute_line(1, 5, 5, False, True).enhanced_deduction == Decimal("5.00")


def test_normal_case_basis_5_fmv_15():
    r = calc.compute_line(1, 15, 5, False, True)
    assert r.enhanced_deduction == Decimal("10.00") and r.extra_benefit_vs_discarding == Decimal("5.00")


def test_twice_basis_cap_basis_2_fmv_20():
    assert calc.compute_line(1, 20, 2, False, True).enhanced_deduction == Decimal("4.00")


def test_25_percent_election_fmv_20():
    r = calc.compute_line(1, 20, None, use_election=True, keeps_inventory=False)
    assert r.basis == Decimal("5.00") and r.enhanced_deduction == Decimal("10.00")
    assert r.extra_benefit_vs_discarding is None and r.extra_benefit_note == calc.ASK_PREPARER


def test_extra_benefit_needs_inventory_and_tax_saved_needs_a_rate():
    assert calc.compute_line(1, 15, 5, False, keeps_inventory=False).extra_benefit_vs_discarding is None
    assert calc.tax_saved(Decimal("5"), None) is None
    assert calc.tax_saved(Decimal("5"), 21) == Decimal("1.05")
    assert calc.dollars(Decimal("10.50")) == 11 and calc.dollars(Decimal("10.49")) == 10


def test_cap_warning_and_carryforward():
    assert calc.cap_check(Decimal("100"), None, "c_corp") is None  # no income entered: no warning
    ok = calc.cap_check(Decimal("100"), 1000, "c_corp")
    assert ok["cap"] == 150.0 and not ok["exceeds_cap"] and "taxable income" in ok["note"]
    over = calc.cap_check(Decimal("200"), 1000, "s_corp")
    assert over["exceeds_cap"] and over["over_cap"] == 50.0 and "carried forward up to 5 years" in over["note"]
    assert "aggregate net income" in over["note"]


# ---------- end to end with menu items ----------

def _menu_id(client, mgr, name):
    return next(m["id"] for m in client.get("/restaurants/me/menu-items", headers=mgr).json() if m["name"] == name)


def deliver(client, menu_name="Rice and black beans", quantity=2, receipt=None, email=EMAILS["restaurant_staff"]):
    """Post by menu item, carry it with the matched volunteer, confirm receipt at the shelter."""
    rest, vol, org = signin(client, email), signin(client, EMAILS["volunteer"]), signin(client, EMAILS["org_manager"])
    mgr = signin(client, EMAILS["restaurant_manager"])
    body = {"quantity": quantity, "unit": "tray", "category": "hot", "attested": True, "menu_item_id": _menu_id(client, mgr, menu_name),
            "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z"}
    r = client.post("/rescues", json=body, headers=rest).json()["rescue"]
    trip = r["trips"][0]
    client.post(f"/trips/{trip['id']}/accept", headers=vol)
    client.post(f"/trips/{trip['id']}/pickup", json={"code": r["pickup_code"], "picked_up_meals": r["est_meals"]}, headers=vol)
    stop = client.get(f"/rescues/{r['id']}", headers=org).json()["trips"][0]["stops"][0]
    client.post(f"/stops/{stop['id']}/deliver", json={"code": stop["dropoff_code"]}, headers=vol)
    rec = client.post(f"/stops/{stop['id']}/receipt", json={"temperature_f": 150, "received_by_name": "Grace",
                                                           **(receipt or {"condition": "accepted"})}, headers=org)
    assert rec.status_code == 200, rec.text
    return r, stop, mgr, org


def summary(client, mgr):
    return client.get("/reports/donor-tax-summary", params={"year": 2026}, headers=mgr).json()


def test_menu_item_fills_valuation_and_only_accepted_quantity_counts(client):
    r, stop, mgr, org = deliver(client, receipt={"condition": "partially_accepted", "received_meals": 12, "reject_reason": "packaging"})
    item = r["items"][0] if "items" in r else None
    s = summary(client, mgr)
    line = s["lines"][0]
    assert line["quantity"] == 1.0                      # 12 of 24 meals accepted = 1 of 2 trays
    assert line["fmv"] == 60.0 and line["fmv_method"] == "own_price_same_item"
    assert line["basis"] == 18.0 and line["basis_method"] == "food_cost_pct"   # 30% food cost (fictional menu)
    assert line["enhanced_deduction"] == 36.0            # min(18 + 21, 36): the 2 x basis cap
    assert line["extra_benefit_vs_discarding"] == 18.0 and line["included"]
    assert s["totals"]["estimated_tax_saved"] == 3.78     # 18 x 21% (rate the fictional restaurant entered)
    assert item is None or item["needs_valuation"] is False


def test_rejected_and_expired_food_count_as_zero(client, fake_clock):
    deliver(client, receipt={"condition": "rejected", "reject_reason": "temperature"})
    mgr = signin(client, EMAILS["restaurant_manager"])
    rest = signin(client, EMAILS["restaurant_staff"])
    client.post("/rescues", json={"quantity": 1, "unit": "tray", "category": "hot", "attested": True,
                                  "menu_item_id": _menu_id(client, mgr, "Rice and black beans"),
                                  "prepared_at": (clock.now() - timedelta(minutes=100)).isoformat() + "Z",
                                  "pickup_deadline": (clock.now() + timedelta(minutes=15)).isoformat() + "Z"}, headers=rest)
    fake_clock.advance(minutes=25)
    with SessionLocal() as db:
        run_jobs(db)
    s = summary(client, mgr)
    assert s["lines"] == [] and s["totals"]["enhanced_deduction"] == 0.0


def test_unverified_recipients_are_excluded(client):
    deliver(client)
    with SessionLocal() as db:
        shelter = db.query(Organization).filter_by(name="Demo Night Shelter").one()
        shelter.receiver_profile.ein_verified = False
        db.commit()
    mgr = signin(client, EMAILS["restaurant_manager"])
    s = summary(client, mgr)
    assert s["lines"][0]["included"] is False
    assert s["lines"][0]["reason"] == "not included in tax estimate: recipient not verified"
    assert s["totals"]["enhanced_deduction"] == 0.0 and s["counts"]["not_verified_recipient_lines"] == 1
    head = client.get("/restaurants/me/benefits", headers=mgr).json()["headline"]
    assert head["value"] == 0 and head["note"] == ""  # nothing to a verified recipient yet, not an "ask your preparer" case


def test_needs_valuation_then_valued(client):
    r, stop, mgr, org = deliver(client)  # valued via the menu
    rest = signin(client, EMAILS["restaurant_staff"])
    q = client.post("/rescues", json={"quantity": 1, "unit": "tray", "category": "hot", "attested": True,
                                      "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z"}, headers=rest).json()
    assert any("left out of tax estimates" in w for w in q["warnings"])
    items = client.get(f"/rescues/{q['rescue']['id']}", headers=mgr).json()["items"]
    assert items[0]["needs_valuation"] is True
    bad = client.patch(f"/rescues/{q['rescue']['id']}/items/{items[0]['id']}/valuation",
                       json={"fmv_per_unit": 50, "fmv_method": "manual_entry", "basis_method": "election_25pct_fmv"}, headers=mgr)
    assert bad.status_code == 422  # Casa keeps inventory: no 25% election
    ok = client.patch(f"/rescues/{q['rescue']['id']}/items/{items[0]['id']}/valuation",
                      json={"fmv_per_unit": 50, "fmv_method": "own_price_similar_item", "basis_per_unit": 15, "basis_method": "actual_cost"},
                      headers=mgr)
    assert ok.json()["needs_valuation"] is False
    assert client.patch(f"/rescues/{q['rescue']['id']}/items/{items[0]['id']}/valuation",
                        json={"fmv_per_unit": 50, "fmv_method": "manual_entry", "basis_per_unit": 1, "basis_method": "actual_cost"},
                        headers=rest).status_code == 403


def test_tax_profile_rules(client):
    mgr = signin(client, EMAILS["restaurant_manager"])
    base = {"entity_type": "c_corp", "keeps_inventory": True, "use_25pct_basis_election": True, "tax_year_start": "2026-01-01"}
    assert client.put("/restaurants/me/tax-profile", json=base, headers=mgr).status_code == 422
    ok = client.put("/restaurants/me/tax-profile", json={**base, "use_25pct_basis_election": False}, headers=mgr).json()
    assert ok["tax_rate_pct"] is None  # never assumed: cleared because the business did not enter it
    assert client.get("/restaurants/me/tax-profile", headers=signin(client, EMAILS["restaurant_staff"])).status_code == 403


def test_cap_warning_on_the_report(client):
    deliver(client)
    mgr = signin(client, EMAILS["restaurant_manager"])
    client.put("/restaurants/me/tax-profile", json={"entity_type": "c_corp", "keeps_inventory": True, "tax_rate_pct": 21,
                                                   "estimated_taxable_income": 100, "tax_year_start": "2026-01-01"}, headers=mgr)
    s = summary(client, mgr)
    assert s["cap"]["cap"] == 15.0 and s["cap"]["exceeds_cap"] and s["cap"]["over_cap"] == s["totals"]["enhanced_deduction"] - 15.0
    assert client.get("/restaurants/me/benefits", headers=mgr).json()["cap_warning"]["exceeds_cap"]


def test_report_totals_equal_the_sum_of_lines_and_formats(client, fake_clock):
    deliver(client)
    fake_clock.advance(minutes=20)
    deliver(client, menu_name="Roast chicken", quantity=1)
    mgr = signin(client, EMAILS["restaurant_manager"])
    s = summary(client, mgr)
    included = [l for l in s["lines"] if l["included"]]
    assert len(s["lines"]) == 2
    assert s["totals"]["enhanced_deduction"] == round(sum(l["enhanced_deduction"] for l in included), 2)
    assert s["totals"]["extra_benefit_vs_discarding"] == round(sum(l["extra_benefit_vs_discarding"] for l in included), 2)
    assert s["totals"]["total_basis_donated"] == round(sum(l["basis"] for l in s["lines"]), 2)
    assert sum(x["enhanced_deduction"] for x in s["subtotals"]) == s["totals"]["enhanced_deduction"]
    assert s["form_8283"]["fields_from_our_records"][0]["cost_or_adjusted_basis"] == s["lines"][0]["basis"]
    pdf = client.get("/reports/donor-tax-summary", params={"year": 2026, "format": "pdf"}, headers=mgr).content
    assert pdf.startswith(b"%PDF") and pdf.count(b"Not tax advice.") >= 1 and b"Form 8283" in pdf
    rows = list(csv.reader(io.StringIO(client.get("/reports/donor-tax-summary", params={"year": 2026, "format": "csv"}, headers=mgr).text)))
    assert rows[0][0] == "date" and ["enhanced_deduction", str(s["totals"]["enhanced_deduction"])] in rows
    assert client.get("/reports/donor-tax-summary", params={"year": 2026}, headers=signin(client, EMAILS["restaurant_staff"])).status_code == 403


def test_acknowledgment_pdf_has_every_field_and_its_hash_is_in_the_audit_log(client):
    deliver(client)
    om = signin(client, EMAILS["org_manager"])
    ack = client.get("/acknowledgments", headers=om).json()[0]
    assert ack["status"] == "pending" and ack["kind"] == "per_delivery"
    signed = client.post(f"/acknowledgments/{ack['id']}/sign", json={"signer_name": "Grace Demo", "signer_title": "Shelter manager"},
                         headers=om).json()
    pdf = client.get(f"/acknowledgments/{ack['id']}/pdf", headers=om).content
    assert hashlib.sha256(pdf).hexdigest() == signed["pdf_sha256"]
    with SessionLocal() as db:
        ev = db.query(AuditEvent).filter_by(action="acknowledgment_signed").one()
        assert ev.details["pdf_sha256"] == signed["pdf_sha256"]
    for needle in (b"Demo Night Shelter Corp. \\(fictional\\)", b"00-0000002", b"Casa Demo Cocina LLC \\(fictional\\)",
                   b"Date\\(s\\) received", b"Rice and black beans", b"section 501\\(c\\)\\(3\\)",
                   b"care of the ill, the needy, or infants", b"money, other property, or services",
                   b"Federal Food, Drug, and", b"Grace Demo, Shelter manager", b"Signer user ID",
                   b"Have a tax professional review this template before real use."):
        assert needle in pdf, needle
    with engine.connect() as conn, pytest.raises(Exception):
        conn.execute(text("UPDATE acknowledgments SET pdf_sha256='x'"))
    assert client.post(f"/acknowledgments/{ack['id']}/sign", json={"signer_name": "X Y", "signer_title": "Z Z"}, headers=om).status_code == 409


def test_monthly_statements_and_reminders(client, fake_clock):
    om = signin(client, EMAILS["org_manager"])
    client.put("/orgs/me/intake/Q3", json={**ORGS["Demo Night Shelter"]["q3"], "acknowledgment_frequency": "monthly"}, headers=om)
    with SessionLocal() as db:  # changing Q3 does not change the EIN; keep the fictional verification
        p = db.query(Organization).filter_by(name="Demo Night Shelter").one().receiver_profile
        assert p.ack_frequency == "monthly" and p.ein_verified
    deliver(client)
    assert client.get("/acknowledgments", headers=om).json() == []
    fake_clock.advance(minutes=8 * 24 * 60)  # into October
    with SessionLocal() as db:
        run_jobs(db)
    om = signin(client, EMAILS["org_manager"])
    acks = client.get("/acknowledgments", headers=om).json()
    assert len(acks) == 1 and acks[0]["kind"] == "monthly" and acks[0]["period_start"] == "2026-09-01"
    fake_clock.advance(minutes=3 * 24 * 60 + 60)
    with SessionLocal() as db:
        run_jobs(db)
        assert db.get(Acknowledgment, acks[0]["id"]).reminders_sent == [3]
    fake_clock.advance(minutes=4 * 24 * 60)
    with SessionLocal() as db:
        run_jobs(db)
        assert db.get(Acknowledgment, acks[0]["id"]).reminders_sent == [3, 7]


def test_decline_acknowledgment(client):
    deliver(client)
    om = signin(client, EMAILS["org_manager"])
    ack = client.get("/acknowledgments", headers=om).json()[0]
    d = client.post(f"/acknowledgments/{ack['id']}/decline", json={"reason": "quantities do not match our log"}, headers=om).json()
    assert d["status"] == "declined"
    assert summary(client, signin(client, EMAILS["restaurant_manager"]))["lines"][0]["acknowledgment"] == "declined"


FIXTURE_BMF = """EIN,NAME,ICO,STREET,CITY,STATE,ZIP,GROUP,SUBSECTION,AFFILIATION,CLASSIFICATION,RULING,DEDUCTIBILITY,FOUNDATION,ACTIVITY,ORGANIZATION,STATUS,TAX_PERIOD,ASSET_CD,INCOME_CD,FILING_REQ_CD,PF_FILING_REQ_CD,ACCT_PD,ASSET_AMT,INCOME_AMT,REVENUE_AMT,NTEE_CD,SORT_NAME
000000002,FICTIONAL DEMO NIGHT SHELTER CORP,,1 DEMO ST,MIAMI,FL,33199,0000,03,3,1000,200001,1,15,000000000,1,01,,0,0,02,0,12,,,,,
000000001,FICTIONAL DEMO FOOD BANK INC,,2 DEMO ST,MIAMI,FL,33199,0000,03,3,1000,200001,1,04,000000000,1,01,,0,0,02,0,12,,,,,
"""


def test_eo_bmf_import_match_and_verification(client):
    admin = signin(client, EMAILS["admin"])
    r = client.post("/admin/eo-bmf/import", params={"source": "FICTIONAL test fixture in EO BMF format"},
                    content=FIXTURE_BMF, headers={**admin, "content-type": "text/csv"})
    assert r.json()["imported"] == 2
    with SessionLocal() as db:
        shelter = db.query(Organization).filter_by(name="Demo Night Shelter").one().id
        bank = db.query(Organization).filter_by(name="Demo Food Bank").one().id
    m = client.get(f"/admin/orgs/{shelter}/irs-match", headers=admin).json()
    assert m["found"] and m["qualified_donee"] and m["record"]["foundation"] == "15" and m["teos_url"].startswith("https://apps.irs.gov")
    v = client.post(f"/admin/orgs/{shelter}/verify-qualified-donee", json={"confirm": True, "method": "eo_bmf"}, headers=admin).json()
    assert v["verified"] and "IRS EO BMF" in v["verification_source"]
    mb = client.get(f"/admin/orgs/{bank}/irs-match", headers=admin).json()
    assert mb["checks"]["not_private_nonoperating_foundation"] is False  # foundation code 04
    assert client.post(f"/admin/orgs/{bank}/verify-qualified-donee", json={"confirm": True, "method": "eo_bmf"}, headers=admin).status_code == 409


def test_roi_calculator_never_assumes_a_rate_or_hauling_cost(client):
    base = {"avg_menu_price": 15, "food_cost_pct": 33.3333, "meals_per_week": 20, "weeks_per_year": 50}
    r = client.post("/tools/donation-roi", json=base).json()
    assert r["yearly"]["estimated_tax_saved"] is None and r["yearly"]["avoided_hauling_cost"] is None
    assert r["yearly"]["enhanced_deduction"] == 10000 and r["yearly"]["extra_deduction_vs_discarding"] == 5000
    assert r["inputs"]["lbs_per_meal"] == 1.2 and "feedingamerica.org" in r["inputs"]["lbs_per_meal_source"]
    with_rate = client.post("/tools/donation-roi", json={**base, "tax_rate_pct": 21, "hauling_cost_per_lb": 0.1}).json()
    assert with_rate["yearly"]["estimated_tax_saved"] == 1050 and with_rate["yearly"]["avoided_hauling_cost"] == 120
    assert "Not tax advice" in r["disclaimer"] and r["formulas"]


def test_state_incentives_empty_and_menu_csv_upload(client):
    assert client.get("/tools/state-incentives").json() == []
    mgr = signin(client, EMAILS["restaurant_manager"])
    body = "name,unit,menu_price_per_unit,food_cost_pct,actual_cost_per_unit,meals_per_unit,category,allergens\n" \
           "Cuban sandwich,box,40,30,,8,cold,gluten;dairy\nRice and black beans,tray,64,30,,12,hot,\nBad row,bucket,1,,,1,hot,\n"
    r = client.post("/restaurants/me/menu-items/csv", content=body, headers={**mgr, "content-type": "text/csv"}).json()
    assert r["created"] == 1 and r["updated"] == 1 and len(r["errors"]) == 1
    staff_view = client.get("/restaurants/me/menu-items", headers=signin(client, EMAILS["restaurant_staff"])).json()
    assert all("menu_price_per_unit" not in m for m in staff_view)  # costs are for managers
