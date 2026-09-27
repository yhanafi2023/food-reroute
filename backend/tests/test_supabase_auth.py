"""Supabase Auth access tokens (app/supabase_auth.py), without a Supabase project: a local ES256 key
stands in for the project's JWKS, and Supabase's GET /auth/v1/user is stubbed."""
from datetime import timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app import auth, clock, config, supabase_auth
from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent, User
from app.seed import reset_database
from tests.helpers import EMAILS

URL = "https://project-ref.supabase.co"
KEY = ec.generate_private_key(ec.SECP256R1())
ALICE, MALLORY = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"


class FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return KEY.public_key()


@pytest.fixture()
def supabase(fake_clock, monkeypatch):
    """Supabase switched on; returns the /auth/v1/user answers, keyed by Supabase user id."""
    monkeypatch.setattr(config, "SUPABASE_URL", URL)
    monkeypatch.setattr(config, "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(config, "SUPABASE_JWKS_URL", f"{URL}/auth/v1/.well-known/jwks.json")
    monkeypatch.setattr(supabase_auth, "_jwks", lambda url: FakeJwks())
    users, calls = {}, []

    def fake_get(url, headers, timeout):
        calls.append(headers)
        assert url == f"{URL}/auth/v1/user" and headers["apikey"] == "sb_publishable_test"
        sub = jwt.decode(headers["Authorization"][7:], options={"verify_signature": False})["sub"]
        return httpx.Response(200, json=users[sub]) if sub in users else httpx.Response(401, json={})

    monkeypatch.setattr(supabase_auth.httpx, "get", fake_get)
    reset_database(with_scenarios=False)
    return users, calls


@pytest.fixture()
def client(supabase):
    with TestClient(app) as c:
        yield c


def token(sub, key=KEY, alg="ES256", iss=f"{URL}/auth/v1", aud="authenticated", minutes=60):
    exp = clock.now().replace(tzinfo=timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode({"sub": sub, "iss": iss, "aud": aud, "exp": exp, "role": "authenticated",
                       "email": EMAILS["volunteer"]}, key, algorithm=alg)


def me(client, tok):
    return client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})


def test_a_confirmed_email_links_once_then_the_supabase_id_is_enough(client, supabase):
    users, calls = supabase
    users[ALICE] = {"id": ALICE, "email": EMAILS["volunteer"].upper(), "email_confirmed_at": "2026-09-01T00:00:00Z"}
    r = me(client, token(ALICE))
    assert r.status_code == 200 and r.json()["email"] == EMAILS["volunteer"]
    with SessionLocal() as db:
        assert db.query(User).filter_by(email=EMAILS["volunteer"]).one().supabase_user_id == ALICE
        assert db.query(AuditEvent).filter_by(action="supabase_account_linked").count() == 1
    users.clear()  # linked: Supabase is not asked again
    assert me(client, token(ALICE)).status_code == 200 and len(calls) == 1


def test_an_unconfirmed_email_or_a_signed_out_session_never_links(client, supabase):
    users, _ = supabase
    users[MALLORY] = {"id": MALLORY, "email": EMAILS["admin"], "email_confirmed_at": None}
    assert me(client, token(MALLORY)).status_code == 401
    del users[MALLORY]  # /auth/v1/user answers 401
    assert me(client, token(MALLORY)).status_code == 401
    with SessionLocal() as db:
        assert db.query(User).filter(User.supabase_user_id.isnot(None)).count() == 0


def test_an_account_already_linked_is_not_taken_over_by_a_second_supabase_user(client, supabase):
    users, _ = supabase
    confirmed = {"email": EMAILS["volunteer"], "email_confirmed_at": "2026-09-01T00:00:00Z"}
    users[ALICE], users[MALLORY] = {"id": ALICE, **confirmed}, {"id": MALLORY, **confirmed}
    assert me(client, token(ALICE)).status_code == 200
    assert me(client, token(MALLORY)).status_code == 401


@pytest.mark.parametrize("bad", [
    dict(key=ec.generate_private_key(ec.SECP256R1())),                  # not this project's key
    dict(iss="https://other-ref.supabase.co/auth/v1"),                  # another project
    dict(aud="anon"),
    dict(key=config.JWT_SECRET, alg="HS256"),                           # forged as a FoodFlow token
])
def test_tokens_not_minted_by_this_project_are_refused(client, supabase, bad):
    users, calls = supabase
    users[ALICE] = {"id": ALICE, "email": EMAILS["volunteer"], "email_confirmed_at": "2026-09-01T00:00:00Z"}
    assert me(client, token(ALICE, **bad)).status_code == 401
    assert calls == []


def test_expired_tokens_ask_to_sign_in_again(client, supabase, fake_clock):
    users, _ = supabase
    users[ALICE] = {"id": ALICE, "email": EMAILS["volunteer"], "email_confirmed_at": "2026-09-01T00:00:00Z"}
    tok = token(ALICE, minutes=5)
    assert me(client, tok).status_code == 200
    fake_clock.advance(minutes=6)
    r = me(client, tok)
    assert r.status_code == 401 and "expired" in r.json()["detail"]


def test_an_unreachable_jwks_answers_503_not_401(client, monkeypatch):
    class Down:
        def get_signing_key_from_jwt(self, token):
            raise jwt.PyJWKClientConnectionError("Fail to fetch data from the url")

    monkeypatch.setattr(supabase_auth, "_jwks", lambda url: Down())
    assert me(client, token(ALICE)).status_code == 503


def test_idempotency_keeps_supabase_users_apart(supabase):
    assert auth.caller_key(f"Bearer {token(ALICE)}") == f"supabase:{ALICE}"
    assert auth.caller_key(f"Bearer {token(MALLORY)}") == f"supabase:{MALLORY}"
    assert auth.caller_key(f"Bearer {token(ALICE, iss='https://evil.example.com/auth/v1')}") == "anon"


def test_supabase_off_leaves_asymmetric_tokens_refused(client, monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    assert me(client, token(ALICE)).status_code == 401


def test_jobs_endpoint_accepts_the_supabase_secret_key_as_apikey(client, monkeypatch):
    monkeypatch.setattr(config, "CRON_SECRET", "")
    monkeypatch.setattr(config, "SUPABASE_SECRET_KEY", "sb_secret_for_tests_0123456789")
    assert client.get("/internal/jobs/run").status_code == 401
    assert client.post("/internal/jobs/run", headers={"apikey": "sb_secret_wrong"}).status_code == 401
    assert client.post("/internal/jobs/run", headers={"Authorization": "Bearer "}).status_code == 401
    r = client.post("/internal/jobs/run", headers={"apikey": "sb_secret_for_tests_0123456789"})
    assert r.status_code == 200 and "no_shows" in r.json()
