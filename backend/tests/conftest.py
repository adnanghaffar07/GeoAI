"""Shared test setup.

Two kinds of tests:
- Tests without a database (health, errors, config, permission policy). They always run.
- Database tests (anything using the `db` fixture). They need `TEST_DATABASE_URL`,
  a PostgreSQL + PostGIS database used only for tests. It is created if missing,
  migrated to the latest version, and emptied after every test.
  In Docker this is set in `.env`, so `docker compose exec api pytest` runs everything.

The job queue is pointed at a closed port, so no test can reach a real queue.
"""

import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL or "postgresql+psycopg://test:test@127.0.0.1:1/test",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "DEPENDENCY_CHECK_TIMEOUT_SECONDS": "1",
        "PUBLIC_APP_URL": "http://testserver",
        # The test client talks plain http, which would not send "Secure" cookies.
        "SESSION_COOKIE_SECURE": "false",
        # Photos uploaded by tests go to a throwaway folder.
        "STORAGE_DIR": tempfile.mkdtemp(prefix="geoinfralens-test-storage-"),
    }
)

# Imported after the environment is set above.
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, make_url, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.core.database import get_session_factory  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Fixtures shared by the analysis and review tests.
pytest_plugins = ["tests.analysis_fixtures"]


@pytest.fixture
def client() -> Iterator[TestClient]:
    # raise_server_exceptions=False lets us test the 500 handler like a real client would see it.
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def make_client() -> Iterator[Callable[[], TestClient]]:
    """Create separate clients, each with its own cookies (one per signed-in person)."""
    app = create_app()
    clients: list[TestClient] = []

    def factory() -> TestClient:
        new_client = TestClient(app, raise_server_exceptions=False)
        clients.append(new_client)
        return new_client

    yield factory
    for created in clients:
        created.close()


def _create_database_if_missing(url: str) -> None:
    parsed = make_url(url)
    maintenance = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    maintenance.dispose()


@pytest.fixture(scope="session")
def database_ready() -> None:
    if not TEST_DATABASE_URL:
        pytest.skip("Database tests need TEST_DATABASE_URL (see tests/conftest.py).")
    _create_database_if_missing(TEST_DATABASE_URL)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture
def db(database_ready: None) -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        table_names = ", ".join(table.name for table in Base.metadata.sorted_tables)
        with get_session_factory()() as cleaner:
            cleaner.execute(text(f"TRUNCATE TABLE {table_names} CASCADE"))
            cleaner.commit()
