"""Shared test fixtures for compute."""

from collections.abc import Generator

import pytest
from compute.models import Base
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Import ServiceConfig to ensure its table is created
from compute.models import ServiceConfig  # noqa: F401


def pytest_addoption(parser: pytest.Parser):
    """Add command line options."""
    parser.addoption(
        "--mqtt-url",
        action="store",
        default="mqtt://mock-broker:1883",
        help="MQTT URL for testing",
    )


@pytest.fixture(scope="session")
def mqtt_url(request: pytest.FixtureRequest) -> str:
    """Get MQTT URL from command line options."""
    return request.config.getoption("--mqtt-url")


@pytest.fixture
def db_engine() -> Generator[Engine, None, None]:
    """Create an in-memory SQLite database engine for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Create a database session for testing."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()
