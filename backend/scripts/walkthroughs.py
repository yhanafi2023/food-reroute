"""Measure the persona walkthroughs for docs/PRACTICALITY.md by running them against the API.

  cd backend && .venv/bin/python -m scripts.walkthroughs

Uses a throwaway SQLite database, the fictional seed, and a fake clock (Friday 7 PM Miami).
Every call is recorded; the step counts in the docs are these numbers.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/walk.db"
os.environ["RUN_SCHEDULER"] = "false"
os.environ.setdefault("ROUTING_PROVIDER", "offline")

import logging  # noqa: E402

logging.disable(logging.INFO)

from fastapi.testclient import TestClient  # noqa: E402

from app import clock  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Notification, User  # noqa: E402
from app.seed import reset_database  # noqa: E402


class Recorder:
    def __init__(self, client):
        self.c, self.calls = client, []

    def __call__(self, method, path, persona_step, **kw):
        r = getattr(self.c, method)(path, **kw)
        self.calls.append((persona_step, method.upper(), path.split("?")[0], r.status_code))
        return r


def code_for(email):
    with SessionLocal() as db:
        u = db.query(User).filter_by(email=email).one()
        n = db.query(Notification).filter_by(user_id=u.id, event="login_code").order_by(Notification.id.desc()).first()
        return n.body.split("Code ")[1][:6]


def signin(rec, email, step):
    rec("post", "/auth/request-code", step, json={"email": email})
    tok = rec("post", "/auth/verify", step, json={"email": email, "code": code_for(email)}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def main():
    clock.set_fake(clock.FakeClock(clock.local_to_utc(datetime(2026, 9, 25, 19, 0))))
    reset_database(with_scenarios=False)
    out = {}
    with TestClient(app) as c:
        rec = Recorder(c)
        # Restaurant staff: sign in, quick post, show pickup code at handoff
        h = signin(rec, "staff@casa-demo.example.com", "restaurant: sign in")
        body = {"quantity": 2, "unit": "tray", "category": "hot", "attested": True,
                "pickup_deadline": (clock.now() + timedelta(minutes=90)).isoformat() + "Z"}
        r = rec("post", "/rescues", "restaurant: quick post (4 fields + attestation)", json=body, headers=h).json()["rescue"]
        rec("get", f"/rescues/{r['id']}", "restaurant: open the rescue to read the pickup code", headers=h)
        out["restaurant"] = list(rec.calls)
        rec.calls.clear()

        # Volunteer: sign in, see offer, accept, pick up with code, deliver with code
        v = signin(rec, "marcus@volunteer-demo.example.com", "volunteer: sign in")
        trips = rec("get", "/volunteers/me/trips", "volunteer: see the offer", headers=v).json()
        t = trips["offers"][0]
        rec("post", f"/trips/{t['id']}/accept", "volunteer: accept", headers=v)
        rec("post", f"/trips/{t['id']}/pickup", "volunteer: enter pickup code and meal count",
            json={"code": r["pickup_code"], "picked_up_meals": 24}, headers=v)
        with SessionLocal() as db:
            from app.models import TripStop
            stop = db.get(TripStop, t["stops"][0]["id"])
            dropoff_code = stop.dropoff_code  # told to the volunteer by the org's staff at the door
        rec("post", f"/stops/{t['stops'][0]['id']}/deliver", "volunteer: enter drop-off code", json={"code": dropoff_code}, headers=v)
        out["volunteer"] = list(rec.calls)
        rec.calls.clear()

        # Org coordinator: sign in, see delivery, confirm receipt with temperature, sign acknowledgment, get report
        o = signin(rec, "manager@shelter-demo.example.com", "org: sign in")
        d = rec("get", "/orgs/me/deliveries", "org: see incoming and to-confirm deliveries", headers=o).json()
        sid = d["to_confirm"][0]["stop"]["id"]
        rec("post", f"/stops/{sid}/receipt", "org: confirm receipt (condition, temperature, name)",
            json={"condition": "accepted", "temperature_f": 150, "received_by_name": "Grace"}, headers=o)
        ack = rec("get", "/acknowledgments", "org: open the donor acknowledgment", headers=o).json()[0]
        rec("post", f"/acknowledgments/{ack['id']}/sign", "org: e-sign it (typed name and title)",
            json={"signer_name": "Grace Demo", "signer_title": "Shelter manager"}, headers=o)
        rep = rec("post", "/orgs/me/reports?start=2026-09-01&end=2026-09-30&format=csv", "org: build this month's report", headers=o).json()
        rec("get", f"/orgs/me/reports/{rep['id']}/download", "org: download the CSV", headers=o)
        out["org"] = list(rec.calls)

    for persona, calls in out.items():
        print(f"\n### {persona}: {len(calls)} API calls\n")
        print("| # | Step | Call | Status |\n|---|---|---|---|")
        for i, (step, m, p, s) in enumerate(calls, 1):
            print(f"| {i} | {step} | `{m} {p}` | {s} |")


if __name__ == "__main__":
    main()
