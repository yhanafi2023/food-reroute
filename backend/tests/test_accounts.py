"""Section 1: passwordless sign-in, roles, organization membership, privacy."""
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Notification, User
from app.seed import reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def _last_code(email):
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email).one()
        n = db.query(Notification).filter_by(user_id=user.id, event="login_code").order_by(Notification.id.desc()).first()
        return n.body.split("Code ")[1][:6], n.body.split("token=")[1].strip()


def test_one_demo_account_per_role(client):
    for role, email in EMAILS.items():
        me = client.get("/auth/me", headers=signin(client, email)).json()
        assert me["role"] == role


def test_email_code_and_magic_link(client, fake_clock):
    r = client.post("/auth/request-code", json={"email": "staff@casa-demo.example.com"})
    assert r.status_code == 200
    code, link = _last_code("staff@casa-demo.example.com")
    assert client.post("/auth/verify", json={"email": "staff@casa-demo.example.com", "code": "000000"}).status_code == 401
    ok = client.post("/auth/verify", json={"email": "staff@casa-demo.example.com", "code": code})
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "restaurant_staff"
    assert client.post("/auth/verify", json={"email": "staff@casa-demo.example.com", "code": code}).status_code == 401  # single use

    client.post("/auth/request-code", json={"email": "staff@casa-demo.example.com"})
    _, link = _last_code("staff@casa-demo.example.com")
    assert client.post("/auth/verify", json={"token": link}).status_code == 200
    assert client.post("/auth/verify", json={"token": link}).status_code == 401  # single use

    client.post("/auth/request-code", json={"email": "staff@casa-demo.example.com"})
    code, _ = _last_code("staff@casa-demo.example.com")
    fake_clock.advance(minutes=11)
    assert client.post("/auth/verify", json={"email": "staff@casa-demo.example.com", "code": code}).status_code == 401  # expired


def test_code_attempts_are_limited(client):
    client.post("/auth/request-code", json={"email": "staff@casa-demo.example.com"})
    code, _ = _last_code("staff@casa-demo.example.com")
    for _ in range(5):
        client.post("/auth/verify", json={"email": "staff@casa-demo.example.com", "code": "999999"})
    assert client.post("/auth/verify", json={"email": "staff@casa-demo.example.com", "code": code}).status_code == 429


def test_unknown_email_does_not_reveal_accounts(client):
    r = client.post("/auth/request-code", json={"email": "nobody@nowhere.example.com"})
    assert r.status_code == 200 and "If that email has an account" in r.json()["message"]


def test_registration_and_manager_staff_management(client):
    r = client.post("/auth/register-organization", json={
        "kind": "restaurant", "organization_name": "New Kitchen (test)", "lat": 25.76, "lng": -80.37,
        "manager_name": "Ana Test", "manager_email": "ana@newkitchen.example.com"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "restaurant_manager"
    mgr = signin_code(client, "ana@newkitchen.example.com")
    add = client.post("/orgs/me/members", json={"email": "cook@newkitchen.example.com", "name": "Cook Test"}, headers=mgr)
    assert add.status_code == 200 and add.json()["role"] == "restaurant_staff"
    members = client.get("/orgs/me/members", headers=mgr).json()
    assert {m["email"] for m in members} == {"ana@newkitchen.example.com", "cook@newkitchen.example.com"}
    staff = signin_code(client, "cook@newkitchen.example.com")
    assert client.get("/orgs/me/members", headers=staff).status_code == 403  # staff cannot manage staff
    assert client.delete(f"/orgs/me/members/{add.json()['id']}", headers=mgr).status_code == 200
    assert client.get("/auth/me", headers=staff).status_code == 401  # deactivated

    other_mgr = signin(client, EMAILS["restaurant_manager"])
    assert client.delete(f"/orgs/me/members/{members[0]['id']}", headers=other_mgr).status_code == 404  # other org


def signin_code(client, email):
    client.post("/auth/request-code", json={"email": email})
    code, _ = _last_code(email)
    return {"Authorization": f"Bearer {client.post('/auth/verify', json={'email': email, 'code': code}).json()['token']}"}


def test_role_boundaries_on_admin_and_profiles(client):
    for role in ("restaurant_staff", "volunteer", "org_staff", "org_manager", "restaurant_manager"):
        assert client.post("/admin/orgs/1/verify-ein", json={"verified": True}, headers=signin(client, EMAILS[role])).status_code == 403
    assert client.get("/volunteers/me/profile", headers=signin(client, EMAILS["restaurant_staff"])).status_code == 403
    assert client.put("/restaurants/me/profile", json={}, headers=signin(client, EMAILS["restaurant_staff"])).status_code in (403, 422)
    assert client.get("/auth/me").status_code == 401


def test_user_org_membership_constraint():
    from sqlalchemy.exc import IntegrityError

    reset_database(with_scenarios=False)
    with SessionLocal() as db:
        db.add(User(email="bad@x.example.com", name="Bad", role="volunteer", organization_id=1))
        with pytest.raises(IntegrityError):
            db.commit()
