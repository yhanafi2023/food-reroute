"""Demo controls: a deterministic clock, admin-only reset and clock changes, sign-in unchanged."""
from datetime import datetime

from fastapi.testclient import TestClient

from app import clock, demo
from app.main import app
from tests.helpers import EMAILS, signin


def test_demo_clock_pause_advance_restart():
    d = demo.DemoClock(datetime(2026, 9, 25, 23, 0))
    d.pause()
    frozen = d.now()
    assert d.now() == frozen
    d.advance(minutes=10)
    assert (d.now() - frozen).total_seconds() == 600
    d.restart()
    assert abs((d.now() - datetime(2026, 9, 25, 23, 0)).total_seconds()) < 1


def test_reset_and_clock_need_an_admin_and_sign_in_is_unchanged():
    installed = demo.DemoClock(demo.start_utc())
    demo._demo = installed
    clock.set_fake(installed)
    try:
        with TestClient(app) as c:
            assert c.post("/demo/reset").status_code in (401, 403)
            assert c.post("/demo/clock", json={"action": "pause"}).status_code in (401, 403)
            staff = signin(c, EMAILS["restaurant_staff"])
            assert c.post("/demo/reset", headers=staff).status_code == 403
            assert c.post("/demo/signin", json={"persona": "restaurant"}).status_code in (404, 405)  # no shortcut sign-in
            admin = signin(c, EMAILS["admin"])
            state = c.post("/demo/reset", headers=admin).json()
            assert state["local_time"].startswith("Fri Sep 25, 7:0")
            admin = signin(c, EMAILS["admin"])
            paused = c.post("/demo/clock", headers=admin, json={"action": "pause"}).json()
            assert paused["running"] is False
            later = c.post("/demo/clock", headers=admin, json={"action": "advance", "minutes": 30}).json()
            assert later["local_time"].startswith("Fri Sep 25, 7:3")
            assert c.get("/time").json()["now"] == later["now"]
    finally:
        demo._demo = None
        clock.set_fake(None)
