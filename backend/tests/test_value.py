"""Restaurant value module: nudges, insights, savings, hauling, monthly report, opt-in marketing."""
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import clock, posting
from app.db import SessionLocal
from app.jobs import run_jobs
from app.main import app
from app.models import MenuItem, Notification, Organization, User
from app.seed import reset_database
from app.value import insights, nudges
from tests.helpers import EMAILS, signin

MON = date(2026, 6, 1)  # a Monday, well before the fake "now" used below


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def at_local(fake_clock, d: date, hh=21, mm=0):
    fake_clock.current = clock.local_to_utc(datetime.combine(d, datetime.min.time()) + timedelta(hours=hh, minutes=mm))


def post_rice(db, fake_clock, d: date, trays: float):
    at_local(fake_clock, d)
    u = db.query(User).filter_by(email=EMAILS["restaurant_staff"]).one()
    rice = db.query(MenuItem).filter_by(organization_id=u.organization_id, name="Rice and black beans").one()
    posting.create_post(db, u, posting.QuickPost(quantity=trays, unit="tray", category="shelf_stable", attested=True,
                                                 menu_item_id=rice.id, pickup_deadline=clock.now() + timedelta(hours=2)))
    db.commit()
    return u.organization_id, rice.id


def build_history(fake_clock, weeks_before=6, weeks_after=0, before=3, after=1, tried=False):
    with SessionLocal() as db:
        for w in range(weeks_before + weeks_after):
            org, rice = post_rice(db, fake_clock, MON + timedelta(weeks=w), before if w < weeks_before else after)
            if tried and w == weeks_before - 1:
                at_local(fake_clock, MON + timedelta(weeks=w, days=1), 10)  # Tuesday after the last 'before' Monday
                insights.tried(db, org, rice, 0, 1)
                db.commit()
        return org, rice


# ---------- nudges ----------

def test_closing_nudge_fires_at_each_restaurants_local_time_and_respects_opt_out(client, fake_clock):
    with SessionLocal() as db:
        casa = db.query(Organization).filter_by(name="Casa Demo Cocina").one()
        pizza = db.query(Organization).filter_by(name="Demo Pizza Sur").one()
        pizza.restaurant_profile.timezone = "America/Los_Angeles"  # closes 10 PM Pacific
        db.commit()
        at_local(fake_clock, date(2026, 9, 25), 21, 15)
        assert nudges.send_due(db) == []                     # 9:15 PM Eastern: too early for Casa (nudge 9:30)
        at_local(fake_clock, date(2026, 9, 25), 21, 40)
        assert nudges.send_due(db) == [casa.id]              # 9:40 PM Eastern
        assert nudges.send_due(db) == []                     # once per day
        at_local(fake_clock, date(2026, 9, 26), 0, 40)       # 12:40 AM Eastern = 9:40 PM Pacific
        assert nudges.send_due(db) == [pizza.id]
        db.commit()
    mgr = signin(client, EMAILS["restaurant_manager"])
    s = client.get("/restaurants/me/value-settings", headers=mgr).json()
    client.put("/restaurants/me/value-settings", json={**s, "nudges_enabled": False}, headers=mgr)
    with SessionLocal() as db:
        at_local(fake_clock, date(2026, 9, 26), 21, 40)
        assert nudges.send_due(db) == [] or db.query(Organization).filter_by(name="Casa Demo Cocina").one().id not in nudges.send_due(db)
        n = db.query(Notification).filter_by(event="closing_nudge").first()
        assert "repeat last post" in n.body


# ---------- insights ----------

def test_no_suggestion_before_four_weeks(client, fake_clock):
    org, _ = build_history(fake_clock, weeks_before=3)
    with SessionLocal() as db:
        assert insights.weekday_patterns(db, org, today=MON + timedelta(weeks=3, days=1)) == []


def test_monday_rice_pattern_is_detected(client, fake_clock):
    org, rice = build_history(fake_clock, weeks_before=6)
    with SessionLocal() as db:
        cards = insights.weekday_patterns(db, org, today=MON + timedelta(weeks=5, days=1))  # Tuesday after the 6th Monday
    assert len(cards) == 1
    c = cards[0]
    assert (c["item"], c["weekday_name"], c["surplus_days"], c["days_checked"], c["average_surplus"]) == \
           ("Rice and black beans", "Monday", 6, 6, 3.0)
    assert c["text"] == ("Rice and black beans: surplus on 6 of the last 6 Mondays, averaging 3.0 trays. "
                         "Consider preparing less on Mondays.")
    assert "not a guarantee" in c["caveat"]


def test_savings_formula_needs_tried_marker_and_cost(client, fake_clock):
    org, rice = build_history(fake_clock, weeks_before=6, weeks_after=4, before=3, after=1, tried=False)
    with SessionLocal() as db:
        assert insights.savings(db, org, today=MON + timedelta(weeks=9, days=1)) == []  # no 'tried it'
    reset_database(with_scenarios=False)
    org, rice = build_history(fake_clock, weeks_before=6, weeks_after=4, before=3, after=1, tried=True)
    with SessionLocal() as db:
        s = insights.savings(db, org, today=MON + timedelta(weeks=9, days=1))[0]  # 4 full weeks after 'tried it'
        assert (s["baseline_per_week"], s["current_per_week"], s["cost_per_unit"]) == (3.0, 1.0, 18.0)  # $60 x 30%
        assert s["estimated_food_cost_saved_per_week"] == 36.0 and "(baseline_surplus - current_surplus) x cost_per_unit" in s["formula"]
        db.get(MenuItem, rice).food_cost_pct = None
        db.commit()
        s2 = insights.savings(db, org, today=MON + timedelta(weeks=9, days=1))[0]
        assert s2["estimated_food_cost_saved_per_week"] is None and "food cost" in s2["note"]


# ---------- hauling, report ----------

def _delivered_month(client):
    from tests.test_tax import deliver
    return deliver(client)


def test_avoided_hauling_needs_an_entered_cost(client):
    _delivered_month(client)
    mgr = signin(client, EMAILS["restaurant_manager"])
    r = client.get("/restaurants/me/value-report", params={"month": "2026-09"}, headers=mgr).json()
    h = r["lines"]["avoided_hauling_cost"]
    assert h["value"] is None and h["status"] == "Add your info to see this"
    s = client.get("/restaurants/me/value-settings", headers=mgr).json()
    client.put("/restaurants/me/value-settings", json={**s, "hauling_cost_per_lb": 0.1}, headers=mgr)
    h2 = client.get("/restaurants/me/value-report", params={"month": "2026-09"}, headers=mgr).json()["lines"]["avoided_hauling_cost"]
    assert h2["value"] == round(28.8 * 0.1, 2) and "x your hauling cost per lb" in h2["formula"]  # 24 meals x 1.2 lbs


def test_monthly_report_total_is_the_sum_of_lines_with_inputs(client):
    _delivered_month(client)
    mgr = signin(client, EMAILS["restaurant_manager"])
    s = client.get("/restaurants/me/value-settings", headers=mgr).json()
    client.put("/restaurants/me/value-settings", json={**s, "hauling_cost_per_lb": 0.1}, headers=mgr)
    r = client.get("/restaurants/me/value-report", params={"month": "2026-09"}, headers=mgr).json()
    L, tot = r["lines"], r["estimated_total_value_this_month"]
    expected = L["avoided_hauling_cost"]["value"] + L["tax_extra_deduction_and_estimated_tax_saved"]["estimated_tax_saved"]
    assert L["food_cost_saved_from_prep_changes"]["status"] == "Add your info to see this"
    assert tot["value"] == round(expected, 2) and set(tot["includes"]) == {"avoided_hauling", "estimated_tax_saved"}
    assert L["community_impact"]["meals_donated"] == 24 and L["community_impact"]["partner_organizations_served"] == 1
    assert L["compliance"]["status"] == "records missing"  # unsigned acknowledgment, no written agreement
    pdf = client.get("/restaurants/me/value-report", params={"month": "2026-09", "format": "pdf"}, headers=mgr).content
    assert pdf.startswith(b"%PDF") and b"Estimated total value this month" in pdf


def test_dumpster_note_only_with_container_info_and_enough_volume(client):
    from app.value.report import hauling

    class P:
        hauling_cost_per_lb = None
        container_size_yd3 = 2.0
        hauling_pickups_per_week = 3
    assert hauling(P, lbs_month=100, days_in_month=30)["right_size_dumpster_note"] is None   # ~0.06 yd3 a week
    assert "Ask your hauler" in hauling(P, lbs_month=4000, days_in_month=30)["right_size_dumpster_note"]
    P.container_size_yd3 = None
    assert hauling(P, lbs_month=4000, days_in_month=30)["right_size_dumpster_note"] is None


# ---------- zero effort ----------

def test_pickup_waits_for_closing_only_when_turned_on_and_safe(client, fake_clock):
    mgr = signin(client, EMAILS["restaurant_manager"])
    s = client.get("/restaurants/me/value-settings", headers=mgr).json()
    client.put("/restaurants/me/value-settings", json={**s, "pickups_after_closing": True}, headers=mgr)
    staff = signin(client, EMAILS["restaurant_staff"])
    cold = client.post("/rescues", json={"quantity": 2, "unit": "box", "category": "shelf_stable", "attested": True,
                                         "form_opened_at": (clock.now() - timedelta(seconds=24)).isoformat() + "Z",
                                         "pickup_deadline": (clock.now() + timedelta(hours=5)).isoformat() + "Z"}, headers=staff).json()
    closing = clock.local_to_utc(datetime(2026, 9, 25, 22, 0))
    for t in cold["rescue"]["trips"]:
        assert datetime.fromisoformat(t["eta_pickup"].rstrip("Z")) >= closing  # never mid-service
    hot = client.post("/rescues", json={"quantity": 1, "unit": "tray", "category": "hot", "attested": True,
                                        "pickup_deadline": (clock.now() + timedelta(hours=2)).isoformat() + "Z"}, headers=staff).json()
    assert any("would not stay safe" in w for w in hot["warnings"])  # hot food is not held until 10 PM
    timing = client.get("/restaurants/me/post-timing", headers=staff).json()
    assert timing["posts_timed"] == 1 and timing["median_seconds"] == 24.0


def test_templates_from_menu_and_tote_program(client):
    staff = signin(client, EMAILS["restaurant_staff"])
    made = client.post("/restaurants/me/templates/from-menu", headers=staff).json()["created"]
    assert set(made) == {"Rice and black beans", "Roast chicken", "Chicken wraps"}
    admin = signin(client, EMAILS["admin"])
    with SessionLocal() as db:
        casa = db.query(Organization).filter_by(name="Casa Demo Cocina").one().id
    assert client.post(f"/admin/restaurants/{casa}/totes/lend", json={"count": 4}, headers=admin).json()["on_hand"] == 10
    t = client.get("/restaurants/me/totes", headers=staff).json()
    assert t["on_hand"] == 10 and t["ledger"][-1]["reason"] == "lent"


# ---------- marketing is opt-in ----------

def test_public_page_social_card_and_qr_expose_nothing_without_opt_in(client):
    _delivered_month(client)
    mgr = signin(client, EMAILS["restaurant_manager"])
    assert client.get("/restaurants/me/social-card", params={"month": "2026-09"}, headers=mgr).status_code == 403
    assert client.get("/restaurants/me/social-card.png", params={"month": "2026-09"}, headers=mgr).status_code == 403
    assert client.get("/restaurants/me/decal-qr.png", headers=mgr).status_code == 403
    s = client.get("/restaurants/me/value-settings", headers=mgr).json()
    client.put("/restaurants/me/value-settings", json={**s, "social_card_enabled": True}, headers=mgr)
    prev = client.get("/restaurants/me/social-card", params={"month": "2026-09"}, headers=mgr).json()
    assert prev["text"] == "This month we shared 24 meals with neighbors in need instead of throwing them away." and not prev["approved"]
    assert client.get("/restaurants/me/social-card.png", params={"month": "2026-09"}, headers=mgr).status_code == 403  # not approved
    client.post("/restaurants/me/social-card/approve", json={"month": "2026-09"}, headers=mgr)
    png = client.get("/restaurants/me/social-card.png", params={"month": "2026-09"}, headers=mgr)
    from PIL import Image
    import io
    assert png.status_code == 200 and Image.open(io.BytesIO(png.content)).size == (1080, 1080)

    prof = client.get("/restaurants/me/profile", headers=mgr).json()
    body = {k: prof[k] for k in ("closing_times", "staffed_until", "totes_on_hand")} | {"public_partner_page": True}
    slug = client.put("/restaurants/me/profile", json=body, headers=mgr).json()["public_slug"]
    page = client.get(f"/public/partners/{slug}").json()
    assert page["meals_donated_to_date"] == 24 and page["partner_organizations"] == [] and page["other_partner_organizations"] == 1
    client.put("/orgs/me/public-naming", json={"consent": True}, headers=signin(client, EMAILS["org_manager"]))
    assert client.get(f"/public/partners/{slug}").json()["partner_organizations"] == ["Demo Night Shelter"]
    qr = client.get("/restaurants/me/decal-qr.png", headers=mgr)
    assert qr.status_code == 200 and qr.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "Tomas" not in str(page) and "Grace" not in str(page)  # no individuals


def test_weekly_insight_and_monthly_report_jobs(client, fake_clock):
    build_history(fake_clock, weeks_before=6)
    at_local(fake_clock, MON + timedelta(weeks=6), 9)  # Monday 9 AM after six Mondays of rice
    with SessionLocal() as db:
        c = run_jobs(db, reports=False)
        assert c["insight_cards"] == 1
    at_local(fake_clock, date(2026, 8, 1), 9)
    with SessionLocal() as db:
        assert run_jobs(db, reports=False)["value_reports"] >= 1
