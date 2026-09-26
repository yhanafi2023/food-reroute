"""SQLAlchemy engine and session. SQLite locally; DATABASE_URL switches to Postgres."""
from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import DATABASE_URL


def _sqlite_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        in_memory = url in ("sqlite://", "sqlite:///:memory:")
        eng = create_engine(url, connect_args={"check_same_thread": False},
                            poolclass=StaticPool if in_memory else None)
        event.listen(eng, "connect", _sqlite_pragmas)
        return eng
    return create_engine(url, pool_pre_ping=True)


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


APPEND_ONLY_SQLITE = [
    "CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END",
]
APPEND_ONLY_POSTGRES = [
    "CREATE OR REPLACE FUNCTION audit_append_only() RETURNS trigger AS $$ "
    "BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql",
    "DROP TRIGGER IF EXISTS audit_no_change ON audit_events",
    "CREATE TRIGGER audit_no_change BEFORE UPDATE OR DELETE ON audit_events "
    "FOR EACH ROW EXECUTE FUNCTION audit_append_only()",
]


def create_schema(eng: Engine = engine) -> None:
    import app.models  # noqa: F401  (register tables)

    Base.metadata.create_all(eng)
    stmts = APPEND_ONLY_SQLITE if eng.dialect.name == "sqlite" else APPEND_ONLY_POSTGRES
    with eng.begin() as conn:
        for s in stmts:
            conn.execute(text(s))


def drop_schema(eng: Engine = engine) -> None:
    import app.models  # noqa: F401

    with eng.begin() as conn:
        # retired sign-in code table, no longer a model: drop it or its foreign key blocks dropping users
        conn.execute(text("DROP TABLE IF EXISTS login_tokens"))
        if eng.dialect.name == "sqlite":
            conn.execute(text("DROP TRIGGER IF EXISTS audit_no_update"))
            conn.execute(text("DROP TRIGGER IF EXISTS audit_no_delete"))
            conn.execute(text("PRAGMA foreign_keys=OFF"))
        else:
            conn.execute(text("DROP TRIGGER IF EXISTS audit_no_change ON audit_events"))
    Base.metadata.drop_all(eng)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
