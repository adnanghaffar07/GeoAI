"""Alembic migration environment.

Uses the app's settings for the database URL and the app's models for
autogenerate. PostGIS system tables (spatial_ref_sys, tiger, topology) are
ignored so autogenerate never tries to drop them.
"""

from logging.config import fileConfig
from typing import Any

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    # Keep the app's own loggers working when migrations run inside the same program (tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
target_metadata = Base.metadata

_IGNORED_SCHEMAS = {"tiger", "tiger_data", "topology"}


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Skip database objects that exist but are not ours (e.g. PostGIS tables)."""
    if type_ == "table":
        if getattr(obj, "schema", None) in _IGNORED_SCHEMAS:
            return False
        if reflected and compare_to is None:
            return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
