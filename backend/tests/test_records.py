"""Sections 9 and 10: tax estimates, acknowledgments, SB 1383, dashboards, org reports, volunteer hours."""
import csv
import io
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.benefits import enhanced_deduction
from app.db import SessionLocal
from app.jobs import run_jobs
from app.main import app
from app.models import OrgReport, Organization
from app.seed import ORGS, reset_database
from tests.helpers import EMAILS, signin
from tests.test_lifecycle import run_full_flow


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def delivered_to_shelter(client):
    r, trip, stop, rest, vol, org = run_full_flow(client)
    ok = client.post(f"/stops/{stop['id']}/receipt", json={"condition": "accepted", "temperature_f": 150,
                                                          "received_by_name": "Tomas"}, headers=org)
    assert ok.status_code == 200
    return r, trip, stop, rest, vol, org


def test_deduction_math():
    assert enhanced_deduction(fmv=9, basis=3) == 6.0          # basis + half the appreciation = 6, cap 2 x 3 = 6
    assert enhanced_deduction(fmv=10, basis=2) == 4.0         # capped at twice the basis
    assert enhanced_deduction(fmv=5, basis=4) == 4.5          # basis + half of 1
    fmv = 4.0
    assert enhanced_deduction(fmv=fmv, basis=0.25 * fmv) == 2.0  # 25% of FMV election: min(1 + 1.5, 2)
    assert enhanced_deduction(fmv=0, basis=0) == 0.0


def test_tax_summary_counts_only_verified_501c3_and_is_labeled(client):
    delivered_to_shelter(client)
    mgr = signin(client, EMAILS["restaurant_manager"])
    s = client.get("/reports/donor-tax-summary", params={"year": 2026}, headers=mgr).json()
    line = s["lines"][0]
    assert line["meals"] == 40 and line["fmv"] == 360.0 and line["basis"] == 120.0   # Casa: $9 FMV, $3 basis per meal (fictional)
    assert line["estimated_deduction"] == 240.0 and s["estimated_total_deduction"] == 240.0
    assert s["disclaimer"] == "Estimate for your tax preparer. Not tax advice." and "15%" in s["limits_note"] and "5 years" in s["limits_note"]
    with SessionLocal() as db:  # un-verify the shelter: it no longer counts
        shelter = db.query(Organization).filter_by(name="Demo Night Shelter").one()
        shelter.receiver_profile.ein_verified = False
        db.commit()
    s2 = client.get("/reports/donor-tax-summary", params={"year": 2026}, headers=mgr).json()
    assert s2["estimated_total_deduction"] == 0 and s2["excluded_unverified_org_lines"] == 1
    assert client.get("/reports/donor-tax-summary", params={"year": 2026}, headers=signin(client, EMAILS["restaurant_staff"])).status_code == 403
    pdf = client.get("/reports/donor-tax-summary", params={"year": 2026, "format": "pdf"}, headers=mgr)
    assert pdf.content.startswith(b"%PDF") and b"Not tax advice" in pdf.content
    assert b"estimated_total_deduction" in client.get("/reports/donor-tax-summary", params={"year": 2026, "format": "csv"}, headers=mgr).content


def test_acknowledgment_has_every_required_field_and_is_signed_by_the_org(client):
    delivered_to_shelter(client)
    om = signin(client, EMAILS["org_manager"])
    ack = client.get("/acknowledgments", headers=om).json()[0]
    c = ack["content"]
    assert c["donor"]["name"] and c["date_received"] and c["food_description"] and c["quantity_meals"] == 40
    assert c["donee"]["legal_name"] == "Demo Night Shelter Corp. (fictional)" and c["donee"]["ein"] == "00-0000002"
    joined = " ".join(c["statements"])
    for phrase in ("care of the ill, the needy, or infants", "not transfer the property in exchange for money",
                   "Federal Food, Drug, and Cosmetic Act"):
        assert phrase in joined
    assert "have a tax professional review" in c["review_note"] and "Not tax advice" in c["disclaimer"]
    assert client.post(f"/acknowledgments/{ack['id']}/sign", json={"signer_name": "Grace"}, headers=signin(client, EMAILS["org_staff"])).status_code == 403
    signed = client.post(f"/acknowledgments/{ack['id']}/sign", json={"signer_name": "Grace Demo"}, headers=om).json()
    assert signed["status"] == "signed"
    assert client.get(f"/acknowledgments/{ack['id']}", params={"format": "pdf"}, headers=signin(client, EMAILS["restaurant_manager"])).content.startswith(b"%PDF")


def test_sb1383_totals(client, fake_clock):
    delivered_to_shelter(client)
    fake_clock.advance(minutes=30)
    delivered_to_shelter(client)
    mgr = signin(client, EMAILS["restaurant_manager"])
    with SessionLocal() as db:
        shelter_id = db.query(Organization).filter_by(name="Demo Night Shelter").one().id
    client.post("/restaurants/me/agreements", json={"receiver_org_id": shelter_id, "signed_date": "2026-09-01",
                                                   "document_url": "https://example.com/agreement.pdf"}, headers=mgr)
    rep = client.get("/reports/sb1383", params={"month": "2026-09"}, headers=mgr).json()
    row = rep["rows"][0]
    with SessionLocal() as db:
        from app.models import TripStop
        received = sum(st.received_meals for st in db.query(TripStop).filter_by(organization_id=shelter_id, status="received"))
    # the shelter's nightly need is 60, so the second delivery was capped at the 20 meals still needed
    assert received == 60
    assert row["organization"] == "Demo Night Shelter" and row["pickups_in_month"] == 2 and row["meals"] == received
    assert row["pounds_recovered"] == round(received * 1.2, 1) and row["food_types"] and "hot" not in row["food_types"]
    assert row["written_agreements"][0]["signed_date"] == "2026-09-01"
    assert "local jurisdiction" in rep["note"] and rep["guidance"].startswith("https://calrecycle.ca.gov")


def test_dashboard_never_assumes_disposal_cost_and_public_page_is_opt_in(client):
    delivered_to_shelter(client)
    mgr = signin(client, EMAILS["restaurant_manager"])
    d = client.get("/restaurants/me/benefits", headers=mgr).json()
    assert d["meals_donated"] == 40 and d["pounds_diverted"] == 48.0 and d["avoided_disposal_cost"] is None
    assert d["acknowledgments"] == {"signed": 0, "pending_signature": 1}
    prof = client.get("/restaurants/me/profile", headers=mgr).json()
    body = {k: prof[k] for k in ("closing_times", "staffed_until", "totes_on_hand")} | {"hauling_cost_per_lb": 0.1, "public_partner_page": True}
    slug = client.put("/restaurants/me/profile", json=body, headers=mgr).json()["public_slug"]
    assert client.get("/restaurants/me/benefits", headers=mgr).json()["avoided_disposal_cost"] == 4.8
    assert client.get(f"/public/partners/{slug}").json()["meals_donated"] == 40
    client.put("/restaurants/me/profile", json={**body, "public_partner_page": False}, headers=mgr)
    assert client.get(f"/public/partners/{slug}").status_code == 404


def _rows(client, h, start="2026-09-01", end="2026-09-30"):
    rep = client.post("/orgs/me/reports", params={"start": start, "end": end, "format": "csv"}, headers=h).json()
    body = client.get(f"/orgs/me/reports/{rep['id']}/download", headers=h).text
    return list(csv.reader(io.StringIO(body))), rep


def test_org_report_has_exactly_the_q3_fields_and_flags_missing_ones(client):
    delivered_to_shelter(client)
    om = signin(client, EMAILS["org_manager"])
    rows, rep = _rows(client, om)
    from app.reports import FIELD_LABELS
    expected = [FIELD_LABELS[f] for f in ORGS["Demo Night Shelter"]["q3"]["required_fields"]] + ["Incomplete fields"]
    assert rows[0] == expected and rep["fields"] == ORGS["Demo Night Shelter"]["q3"]["required_fields"]
    assert rows[1][expected.index("Received by")] and rows[1][-1] == ""
    new_q3 = {**ORGS["Demo Night Shelter"]["q3"], "required_fields": ORGS["Demo Night Shelter"]["q3"]["required_fields"] + ["allergen_info"]}
    client.put("/orgs/me/intake/Q3", json=new_q3, headers=om)
    rows2, _ = _rows(client, om)
    assert rows2[1][-1] == "allergen_info"  # the post did not declare allergens
    stop_id = client.get("/orgs/me/incomplete-deliveries", headers=om).json()[0]["stop_id"]
    r2 = run_full_flow(client)[2]
    form = client.get(f"/stops/{r2['id']}/receipt-form", headers=om).json()
    assert "allergen_info" in form["prompt"] and stop_id


def test_scheduled_reports_follow_each_orgs_frequency(client):
    delivered_to_shelter(client)
    with SessionLocal() as db:
        run_jobs(db)
        by_org = {r.organization_id: r for r in db.query(OrgReport).all()}
        shelter = db.query(Organization).filter_by(name="Demo Night Shelter").one()
        bank = db.query(Organization).filter_by(name="Demo Food Bank").one()
        assert by_org[shelter.id].format == "pdf" and by_org[shelter.id].row_count == 1   # per delivery, PDF
        assert by_org[bank.id].format == "csv" and by_org[bank.id].period_start.day == 1   # monthly, CSV


def test_volunteer_hours_export(client, fake_clock):
    delivered_to_shelter(client)
    vol = signin(client, EMAILS["volunteer"])
    h = client.get("/volunteers/me/hours", headers=vol).json()
    assert len(h["trips"]) == 1 and h["trips"][0]["hours"] >= 0 and h["total_hours"] == h["trips"][0]["hours"]
    assert client.get("/volunteers/me/hours", params={"format": "csv"}, headers=vol).text.startswith("date,started")
    assert client.get("/volunteers/me/hours", headers=signin(client, EMAILS["org_staff"])).status_code == 403
    _ = timedelta
    _ = clock
