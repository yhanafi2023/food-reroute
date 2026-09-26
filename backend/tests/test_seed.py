"""Section 12: the seeded demo contains every required scenario, produced by the real services."""
import pytest

from app.db import SessionLocal
from app.models import AuditEvent, Organization, ReceiverProfile, Rescue, Trip, TripStop, User, VolunteerProfile
from app.seed import reset_database


@pytest.fixture(scope="module")
def seeded():
    reset_database(with_scenarios=True)
    with SessionLocal() as db:
        yield db


def test_fictional_accounts_per_spec(seeded):
    db = seeded
    assert db.query(Organization).filter_by(kind="restaurant").count() == 5
    assert db.query(Organization).filter_by(kind="receiver").count() == 4
    assert all(o.is_fictional for o in db.query(Organization))
    assert db.query(VolunteerProfile).count() == 6
    for role in ("restaurant_staff", "restaurant_manager", "volunteer", "org_staff", "org_manager", "admin"):
        assert db.query(User).filter_by(role=role, is_demo_account=True).count() >= 1
    profiles = {p.organization.name: p for p in db.query(ReceiverProfile)}
    assert profiles["Demo Food Bank"].accepts_hot is False and profiles["Demo Food Bank"].schedule["sun"] == []
    assert profiles["Demo Night Shelter"].accepts_hot and "temperature_at_receipt" in profiles["Demo Night Shelter"].required_fields
    assert profiles["Demo Community Fridge"].schedule["mon"] == [["00:00", "24:00"]] and profiles["Demo Community Fridge"].curbside_ok
    assert profiles["Demo Community Fridge"].accepts_hot is False and profiles["Demo Community Fridge"].accepts_frozen is False
    assert profiles["Demo Halal Pantry"].dietary_rules == ["halal_only"]


def test_completed_rescue_with_full_audit_trail(seeded):
    r = seeded.query(Rescue).join(Organization, Organization.id == Rescue.restaurant_org_id).filter(Organization.name == "Casa Demo Cocina").first()
    assert r.status == "received"
    actions = [e.action for e in seeded.query(AuditEvent).filter_by(rescue_id=r.id)]
    for a in ("rescue_posted", "trip_matched", "trip_en_route_pickup", "trip_picked_up", "stop_delivered", "stop_received", "rescue_received"):
        assert a in actions


def test_no_show_requeued(seeded):
    ev = seeded.query(AuditEvent).filter_by(action="volunteer_no_show").all()
    assert ev and seeded.query(AuditEvent).filter_by(rescue_id=ev[0].rescue_id, action="requeued").count() >= 1
    assert seeded.get(Rescue, ev[0].rescue_id).status == "received"


def test_partial_acceptance(seeded):
    s = seeded.query(TripStop).filter_by(condition="partially_accepted").one()
    assert s.received_meals == 12 and s.reject_reason == "packaging"


def test_late_night_simulated_av_delivery_and_missed_window_fallback(seeded):
    av = seeded.query(Trip).filter_by(mode="waymo_sim", status="received").all()
    assert av and all(t.simulated for t in av) and av[0].handoff_state == "received"
    missed = seeded.query(AuditEvent).filter_by(action="av_load_window_missed").one()
    r = seeded.get(Rescue, missed.rescue_id)
    modes = [(t.mode, t.status) for t in r.trips]
    assert ("waymo_sim", "reassigned") in modes and ("volunteer", "received") in modes
