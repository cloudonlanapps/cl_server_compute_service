"""Database configuration with WAL mode support for multi-process access."""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker
import os

if TYPE_CHECKING:
    from .config import ComputeConfigBase


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


from sqlalchemy.pool import StaticPool

def create_db_engine(
    db_url: str,
    *,
    echo: bool = False,
) -> Engine:
    """Create SQLAlchemy engine with WAL mode for SQLite.

    Args:
        db_url: Database URL (SQLite or other)
        echo: Enable SQL query logging

    Returns:
        SQLAlchemy engine instance
    """
    kwargs = {
        "connect_args": {"check_same_thread": False},
        "echo": echo,
    }

    # For in-memory SQLite, use StaticPool to persist state across connections
    if db_url == "sqlite:///:memory:":
        kwargs["poolclass"] = StaticPool

    engine = create_engine(db_url, **kwargs)

    # Register WAL mode listener for SQLite
    if db_url.lower().startswith("sqlite") and db_url != "sqlite:///:memory:":
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


# Global engine and session factory - initialized in main.py via init_db
engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def init_db(config: ComputeConfigBase) -> None:
    """Initialize database engine and session factory.

    Args:
        config: Service configuration
    """
    global engine, SessionLocal

    if engine is not None:
        return

    logger.info(f"Initializing database: {config.database_url}")
    
    # Pre-flight check for DB lock (SQLite only)
    if config.database_url.startswith("sqlite"):
        try:
             check_db_lock(config.database_url)
        except Exception as e:
             logger.warning(f"Database lock check warning: {e}")

    engine = create_db_engine(config.database_url, echo=config.debug)
    SessionLocal = create_session_factory(engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session for FastAPI dependency injection."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    yield from get_db_session(SessionLocal)


def check_tables_exist() -> None:
    """Check that required database tables exist.

    This should be called on server startup to ensure migrations have been run.

    Raises:
        RuntimeError: If required tables don't exist
    """
    from sqlalchemy import inspect

    if engine is None:
        raise RuntimeError("Database not initialized")

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


def check_db_lock(db_url: str, timeout: int = 2) -> None:
    """Check if SQLite database is locked by another process.
    
    Args:
        db_url: Database URL
        timeout: Timeout in seconds
        
    Raises:
        RuntimeError: If database is locked
    """
    if not db_url.startswith("sqlite:///"):
        return
        
    path = db_url.replace("sqlite:///", "")
    if path == ":memory:":
        return
        
    if not os.path.exists(path):
        return

    # Attempt to acquire a lock by running a simple immediate transaction
    # This is a "canary" test to see if the DB is write-locked by a zombie process
    import sqlite3
    
    try:
        # Connect with short timeout
        conn = sqlite3.connect(path, timeout=timeout)
        try:
            cursor = conn.cursor()
            # BEGIN IMMEDIATE tries to get a RESERVED lock immediately
            # If a WAL writer is active, this might fail or wait
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute("ROLLBACK")
        finally:
            conn.close()
    except sqlite3.OperationalError as e:
         if "locked" in str(e):
             logger.error(f"Database {path} is LOCKED by another process!")
             logger.error("This usually means a 'compute-worker' or server process did not shut down cleanly.")
             logger.error("Run with '--force' to kill zombie processes.")
             raise RuntimeError(f"Database is locked: {e}")
         else:
             logger.warning(f"Database check failed (non-lock error): {e}")


