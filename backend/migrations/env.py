"""Alembic environment: the database URL comes from DATABASE_URL (app/config.py), the schema from app/models.py."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import DATABASE_URL
from app.db import Base
import app.models  # noqa: F401  (register tables)

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    # tests and tools may pass a URL explicitly: alembic -x url=sqlite:///...
    return context.get_x_argument(as_dictionary=True).get("url") or config.attributes.get("url") or DATABASE_URL


def run_migrations_offline() -> None:
    """Emit SQL instead of running it: alembic upgrade head --sql"""
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, render_as_batch=_url().startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
