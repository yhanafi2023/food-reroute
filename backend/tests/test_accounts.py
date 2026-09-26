"""Section 1: email and password sign-in, roles, organization membership, privacy."""
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.db import SessionLocal
from app.main import app
from app.models import IdempotencyRecord, Notification, User
from app.seed import DEMO_PASSWORD, reset_database
from tests.helpers import EMAILS, signin


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _volunteer(client, email="new@volunteer.example.com", password="correct horse battery"):
    return client.post("/auth/register-volunteer", json={
        "name": "Val Test", "email": email, "password": password, "home_lat": 25.76, "home_lng": -80.37})


def test_one_demo_account_per_role(client):
    for role, email in EMAILS.items():
        me = client.get("/auth/me", headers=signin(client, email)).json()
        assert me["role"] == role


def test_email_and_password_sign_in(client):
    ok = _login(client, "staff@casa-demo.example.com", DEMO_PASSWORD)
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "restaurant_staff"
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {ok.json()['token']}"}).status_code == 200
    assert _login(client, "STAFF@Casa-Demo.example.com", DEMO_PASSWORD).status_code == 200  # email is case-insensitive

    wrong = _login(client, "staff@casa-demo.example.com", "not-the-password")
    unknown = _login(client, "nobody@nowhere.example.com", DEMO_PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Incorrect email or password"}  # does not reveal accounts
    assert client.post("/auth/login", json={"email": "staff@casa-demo.example.com"}).status_code == 422


def test_registration_stores_a_password_hash_and_signs_in(client):
    r = _volunteer(client)
    assert r.status_code == 200, r.text
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()["role"] == "volunteer"
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="new@volunteer.example.com").one()
        assert "correct horse battery" not in user.password_hash
        assert user.password_hash.startswith("pbkdf2_sha256$")
        assert db.query(Notification).filter_by(user_id=user.id).count() == 0  # no email or code is sent
    assert _login(client, "new@volunteer.example.com", "correct horse battery").status_code == 200
    assert _login(client, "new@volunteer.example.com", "correct horse batter").status_code == 401

    assert _volunteer(client).status_code == 409  # same email again
    short = _volunteer(client, email="short@volunteer.example.com", password="seven77")
    assert short.status_code == 422 and "password" in short.text
    with SessionLocal() as db:
        assert db.query(User).filter_by(email="short@volunteer.example.com").count() == 0


def test_stored_hash_keeps_its_own_work_factor(monkeypatch):
    monkeypatch.setattr(auth, "PASSWORD_ITERATIONS", 2_000)
    old = auth.hash_password("pw-before-upgrade")
    monkeypatch.setattr(auth, "PASSWORD_ITERATIONS", 3_000)
    assert old.split("$")[1] == "2000" and auth.verify_password("pw-before-upgrade", old)
    assert auth.hash_password("same") != auth.hash_password("same")  # salted
    for broken in ("", "plaintext", "md5$1$abc$def", "pbkdf2_sha256$x$abc$def", "pbkdf2_sha256$1000$!!$!!"):
        assert auth.verify_password("plaintext", broken) is False


def test_demo_accounts_sign_in_only_in_demo_mode(client, monkeypatch):
    assert _volunteer(client).status_code == 200
    monkeypatch.setattr(auth, "DEMO_MODE", False)
    r = _login(client, EMAILS["admin"], DEMO_PASSWORD)
    assert r.status_code == 403 and "DEMO_MODE" in r.json()["detail"]
    assert _login(client, "new@volunteer.example.com", "correct horse battery").status_code == 200  # real accounts work


def test_sign_in_responses_are_never_stored_or_replayed(client):
    key = {"Idempotency-Key": "same-key"}
    first = client.post("/auth/login", json={"email": EMAILS["volunteer"], "password": DEMO_PASSWORD}, headers=key)
    second = client.post("/auth/login", json={"email": EMAILS["admin"], "password": "wrong-password"}, headers=key)
    assert first.status_code == 200 and second.status_code == 401  # not handed the first caller's session
    with SessionLocal() as db:
        assert db.query(IdempotencyRecord).count() == 0


def test_registration_and_manager_staff_management(client):
    r = client.post("/auth/register-organization", json={
        "kind": "restaurant", "organization_name": "New Kitchen (test)", "lat": 25.76, "lng": -80.37,
        "manager_name": "Ana Test", "manager_email": "ana@newkitchen.example.com", "manager_password": "ana-password"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "restaurant_manager"
    mgr = signin(client, "ana@newkitchen.example.com", "ana-password")
    assert client.post("/orgs/me/members", json={"email": "cook@newkitchen.example.com", "name": "Cook Test"},
                       headers=mgr).status_code == 422  # a new member needs a password
    add = client.post("/orgs/me/members", json={"email": "cook@newkitchen.example.com", "name": "Cook Test",
                                                "password": "cook-password"}, headers=mgr)
    assert add.status_code == 200 and add.json()["role"] == "restaurant_staff"
    members = client.get("/orgs/me/members", headers=mgr).json()
    assert {m["email"] for m in members} == {"ana@newkitchen.example.com", "cook@newkitchen.example.com"}
    assert all("password" not in key for m in members for key in m)
    staff = signin(client, "cook@newkitchen.example.com", "cook-password")
    assert client.get("/orgs/me/members", headers=staff).status_code == 403  # staff cannot manage staff
    assert client.delete(f"/orgs/me/members/{add.json()['id']}", headers=mgr).status_code == 200
    assert client.get("/auth/me", headers=staff).status_code == 401  # deactivated
    assert _login(client, "cook@newkitchen.example.com", "cook-password").status_code == 401  # and cannot sign in

    other_mgr = signin(client, EMAILS["restaurant_manager"])
    assert client.delete(f"/orgs/me/members/{members[0]['id']}", headers=other_mgr).status_code == 404  # other org


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
        db.add(User(email="bad@x.example.com", password_hash="x", name="Bad", role="volunteer", organization_id=1))
        with pytest.raises(IntegrityError):
            db.commit()


def test_every_account_has_a_password():
    from sqlalchemy.exc import IntegrityError

    reset_database(with_scenarios=False)
    with SessionLocal() as db:
        db.add(User(email="nopass@x.example.com", name="No Pass", role="volunteer"))
        with pytest.raises(IntegrityError):
            db.commit()
