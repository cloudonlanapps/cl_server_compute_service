"""Database configuration with WAL mode support for multi-process access."""

from __future__ import annotations

from collections.abc import Callable, Generator

from cl_server_shared.config import Config
from loguru import logger
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker


def enable_wal_mode(
    dbapi_conn: DBAPIConnection,
    connection_record: object,
) -> None:
    """Enable WAL mode and set optimization pragmas for SQLite.

    This function should be registered as an event listener on SQLite engines.
    WAL mode enables concurrent reads and single writer, critical for multi-process access.
    """
    _ = connection_record
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=30000000000")
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_db_engine(
    database_url: str,
    *,
    echo: bool = False,
) -> Engine:
    """Create SQLAlchemy engine with WAL mode for SQLite.

    Args:
        database_url: Database URL (SQLite or other)
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy engine instance
    """
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        echo=echo,
    )

    # Register WAL mode listener for SQLite
    if database_url.lower().startswith("sqlite"):
        event.listen(engine, "connect", enable_wal_mode)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create session factory from engine.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Session factory
    """
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
    )


def get_db_session(
    session_factory: Callable[[], Session],
) -> Generator[Session, None, None]:
    """Database session dependency for FastAPI.

    Args:
        session_factory: Session factory callable

    Yields:
        Database session
    """
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


# Create engine with WAL mode - use WORKER_DATABASE_URL for task management
engine = create_db_engine(Config.WORKER_DATABASE_URL, echo=False)

SessionLocal: sessionmaker[Session] = create_session_factory(engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session for FastAPI dependency injection."""
    yield from get_db_session(SessionLocal)


def check_tables_exist() -> None:
    """Check that required database tables exist.

    This should be called on server startup to ensure migrations have been run.

    Raises:
        RuntimeError: If required tables don't exist
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    required_tables = ["jobs", "queue_entries", "service_config", "alembic_version"]

    missing_tables = [
        table for table in required_tables if table not in existing_tables
    ]

    if missing_tables:
        msg = (
            f"Database tables missing: {', '.join(missing_tables)}\n"
            "Please run database migrations first:\n"
            "  uv run compute-migrate"
        )
        logger.error(msg)
        raise RuntimeError(msg)
