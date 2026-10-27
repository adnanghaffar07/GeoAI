"""Database engine, sessions, and connectivity check (sync SQLAlchemy).

The same engine and session factory are used by API routes and Celery workers.
"""

import logging
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    """Create the engine once. Connections are checked before use (`pool_pre_ping`)."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.dependency_check_timeout_seconds},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request.

    If the request raises, the transaction is rolled back so no partial changes
    are saved. Routes commit explicitly when their work succeeds.
    """
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database() -> bool:
    """Return True if the database answers a trivial query, False otherwise."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        # One clear line (no traceback): this is an expected state, e.g. the database is starting.
        cause = exc.__cause__ or exc  # the driver's own message is the clearest
        reason = (str(cause).strip().splitlines() or ["unknown error"])[0]
        logger.warning("Database not reachable: %s", reason)
        return False
