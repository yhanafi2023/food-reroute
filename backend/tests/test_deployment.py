"""Deployment (Vercel + Supabase) regressions, checked without a Postgres server: connection
settings, required secrets, Postgres-portable schema, migrations, the demo-reset guard, the
login throttle, and the scheduled-jobs endpoint with its lease."""
import io
import re
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Boolean, CheckConstraint, create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable

from app import auth, clock, config, db as app_db, jobs, seed
from app.db import Base, SessionLocal
from app.main import app
from app.models import JobLock, LoginAttempt, User
from app.seed import DEMO_PASSWORD, reset_database
from tests.helpers import EMAILS

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(fake_clock):
    reset_database(with_scenarios=False)
    with TestClient(app) as c:
        yield c


def _alembic(url, output=None):
    cfg = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.attributes.update(url=url, configure_logger=False)
    return cfg


# --- connection settings -------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("postgres://u:p@db.x.supabase.co:5432/postgres", "postgresql+psycopg://u:p@db.x.supabase.co:5432/postgres"),
    ("postgresql://u:p@pooler.supabase.com:6543/postgres", "postgresql+psycopg://u:p@pooler.supabase.com:6543/postgres"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("sqlite:///./foodflow.db", "sqlite:///./foodflow.db"),
])
def test_database_urls_use_the_installed_psycopg_driver(raw, expected):
    assert config.database_url(raw) == expected


@pytest.mark.parametrize("serverless", [False, True])
def test_postgres_engine_suits_the_supabase_pooler(serverless, monkeypatch):
    seen = {}
    monkeypatch.setattr(app_db, "SERVERLESS", serverless)
    monkeypatch.setattr(app_db, "create_engine", lambda url, **kw: seen.update(kw) or create_engine(url, **kw))
    eng = app_db.make_engine("postgresql+psycopg://u:p@localhost:6543/postgres")  # no connection is made
    assert eng.dialect.driver == "psycopg"
    assert seen["connect_args"] == {"prepare_threshold": None}  # transaction pooler: no prepared statements
    assert (seen.get("poolclass") is NullPool) is serverless


@pytest.mark.parametrize("demo,serverless,secret,ok", [
    (True, False, config.DEV_JWT_SECRET, True),            # local demo: the dev default is fine
    (False, False, config.DEV_JWT_SECRET, False),
    (False, False, "replace-with-a-long-random-string", False),
    (False, False, "short", False),
    (True, True, config.DEV_JWT_SECRET, False),            # anything on Vercel needs a real secret
    (False, True, "x" * 48, True),
])
def test_app_refuses_to_start_with_a_guessable_jwt_secret(demo, serverless, secret, ok, monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", demo)
    monkeypatch.setattr(config, "SERVERLESS", serverless)
    monkeypatch.setattr(config, "JWT_SECRET", secret)
    if ok:
        config.check_secrets()
    else:
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            config.check_secrets()


# --- schema and migrations -----------------------------------------------------------------

def test_every_table_compiles_for_postgres_and_checks_never_compare_booleans_to_numbers():
    for table in Base.metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        booleans = [c.name for c in table.columns if isinstance(c.type, Boolean)]
        for check in (c for c in table.constraints if isinstance(c, CheckConstraint)):
            for col in booleans:  # "flag = 1" works in SQLite but is an error in Postgres
                assert not re.search(rf"\b{col}\s*(=|!=|<>)\s*\d", str(check.sqltext)), (table.name, check.name)


def test_migrations_build_exactly_the_models_and_downgrade_cleanly(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(_alembic(url), "head")
    eng = create_engine(url)
    with eng.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        triggers = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger'"))}
        assert {"audit_no_update", "audit_no_delete"} <= triggers
    command.downgrade(_alembic(url), "base")
    assert set(inspect(create_engine(url)).get_table_names()) == {"alembic_version"}


def test_migration_renders_postgres_sql_with_the_audit_trigger():
    out = io.StringIO()
    command.upgrade(_alembic("postgresql+psycopg://u:p@localhost:5432/db", out), "head", sql=True)
    sql = out.getvalue()
    assert sql.count("CREATE TABLE") == len(Base.metadata.tables) + 1  # + alembic_version
    assert "CREATE TRIGGER audit_no_change BEFORE UPDATE OR DELETE ON audit_events" in sql


def test_demo_mode_never_drops_tables_outside_sqlite(monkeypatch):
    class FakeDialect:
        name = "postgresql"

    class FakeEngine:
        dialect = FakeDialect()

    resets = []
    monkeypatch.setattr(seed, "engine", FakeEngine())
    monkeypatch.setattr(seed, "schema_is_current", lambda: False)
    monkeypatch.setattr(seed, "reset_database", lambda: resets.append(True))
    monkeypatch.setattr(seed, "inspect", lambda _eng: type("I", (), {"get_table_names": lambda self: ["users"]})())
    with pytest.raises(RuntimeError, match="will not drop it"):
        seed.seed_if_empty()
    assert resets == []
    monkeypatch.setattr(seed, "inspect", lambda _eng: type("I", (), {"get_table_names": lambda self: []})())
    seed.seed_if_empty()  # an empty database may still be created and seeded
    assert resets == [True]


# --- login throttle ------------------------------------------------------------------------

def _login(client, email, password, headers=None):
    return client.post("/auth/login", json={"email": email, "password": password}, headers=headers or {})


def test_repeated_wrong_passwords_lock_that_email_for_the_window(client, fake_clock):
    email = EMAILS["restaurant_staff"]
    for _ in range(auth.MAX_FAILURES_PER_EMAIL):
        assert _login(client, email, "wrong-password").status_code == 401
    locked = _login(client, email, DEMO_PASSWORD)  # even the right password waits
    assert locked.status_code == 429 and "Try again in 15 minutes" in locked.json()["detail"]
    assert _login(client, EMAILS["volunteer"], DEMO_PASSWORD).status_code == 200  # other accounts unaffected
    fake_clock.advance(minutes=auth.THROTTLE_WINDOW_MIN + 1)
    assert _login(client, email, DEMO_PASSWORD).status_code == 200


def test_success_clears_the_failures_for_that_email(client):
    email = EMAILS["restaurant_staff"]
    for _ in range(auth.MAX_FAILURES_PER_EMAIL - 1):
        _login(client, email, "wrong-password")
    assert _login(client, email, DEMO_PASSWORD).status_code == 200
    assert _login(client, email, "wrong-password").status_code == 401  # counting restarted
    assert _login(client, email, DEMO_PASSWORD).status_code == 200


def test_one_address_trying_many_emails_is_throttled(client):
    for i in range(auth.MAX_FAILURES_PER_IP):
        assert _login(client, f"guess{i}@nowhere.example.com", "wrong-password").status_code == 401
    assert _login(client, EMAILS["admin"], DEMO_PASSWORD).status_code == 429


def test_behind_vercel_the_caller_address_comes_from_x_real_ip(client, monkeypatch):
    monkeypatch.setattr(auth, "SERVERLESS", True)
    _login(client, "nobody@nowhere.example.com", "wrong-password", headers={"x-real-ip": "203.0.113.7"})
    monkeypatch.setattr(auth, "SERVERLESS", False)
    _login(client, "nobody@nowhere.example.com", "wrong-password", headers={"x-real-ip": "198.51.100.1"})
    with SessionLocal() as db:
        keys = {a.key for a in db.query(LoginAttempt).all()}
    assert "ip:203.0.113.7" in keys and "ip:testclient" in keys
    assert "ip:198.51.100.1" not in keys  # the header is not trusted off Vercel


# --- scheduled jobs endpoint ---------------------------------------------------------------

def test_jobs_endpoint_is_off_without_a_cron_secret(client, monkeypatch):
    monkeypatch.setattr(config, "CRON_SECRET", "")
    assert client.get("/internal/jobs/run", headers={"Authorization": "Bearer "}).status_code == 404


def test_jobs_endpoint_requires_the_secret_and_runs_the_jobs(client, monkeypatch):
    monkeypatch.setattr(config, "CRON_SECRET", "cron-secret-for-tests-0123456789")
    assert client.get("/internal/jobs/run").status_code == 401
    assert client.get("/internal/jobs/run", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = {"Authorization": "Bearer cron-secret-for-tests-0123456789"}
    for method in ("get", "post"):  # Vercel Cron sends GET; pg_net can POST
        r = getattr(client, method)("/internal/jobs/run", headers=ok)
        assert r.status_code == 200 and "no_shows" in r.json()
    with SessionLocal() as db:
        assert db.get(JobLock, "jobs").locked_until <= clock.now()  # released after the run


def test_overlapping_runs_are_skipped_and_old_login_attempts_pruned(client, monkeypatch):
    with SessionLocal() as db:
        db.add_all([LoginAttempt(key="email:old@x.example.com", at=clock.now() - timedelta(hours=25)),
                    LoginAttempt(key="email:new@x.example.com", at=clock.now())])
        db.commit()
        first, second = SessionLocal(), SessionLocal()
        try:
            assert jobs._take_lock(first) is True
            assert jobs.run_jobs_exclusive(second) == {"skipped": "another run is in progress"}
            jobs._release_lock(first)
            assert "no_shows" in jobs.run_jobs_exclusive(second)
        finally:
            first.close()
            second.close()
        assert {a.key for a in db.query(LoginAttempt).all()} == {"email:new@x.example.com"}


# --- first admin ---------------------------------------------------------------------------

def test_create_admin_script_makes_an_admin_who_can_sign_in(client):
    from scripts.create_admin import create_admin

    create_admin(" Boss@FoodFlow.example.org ", "Real Admin", "a-long-admin-password")
    r = _login(client, "boss@foodflow.example.org", "a-long-admin-password")
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    with pytest.raises(SystemExit, match="already exists"):
        create_admin("boss@foodflow.example.org", "Again", "a-long-admin-password")
    with pytest.raises(SystemExit, match="8 to 128"):
        create_admin("other@foodflow.example.org", "Short", "short")
    with SessionLocal() as db:
        assert db.query(User).filter_by(role="admin").count() == 2  # the demo admin plus this one
