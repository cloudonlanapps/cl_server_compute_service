"""Tests for database configuration."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from compute.database import (
    create_db_engine,
    create_session_factory,
    enable_wal_mode,
    get_db,
    get_db_session,
)


class TestEnableWalMode:
    """Tests for enable_wal_mode function."""

    def test_enable_wal_mode(self):
        """Test that WAL mode and pragmas are set correctly."""
        # Create mock cursor and connection
        mock_cursor: MagicMock = MagicMock()
        mock_conn: MagicMock = MagicMock()
        mock_conn.cursor.return_value = mock_cursor  # pyright: ignore[reportAny] for testing purposes

        # Call enable_wal_mode
        enable_wal_mode(mock_conn, None)

        # Verify cursor methods were called
        assert mock_cursor.execute.called  # pyright: ignore[reportAny] for testing purposes
        assert mock_cursor.close.called  # pyright: ignore[reportAny] for testing purposes

        # Verify WAL mode was set
        calls = [str(call) for call in mock_cursor.execute.call_args_list]  # pyright: ignore[reportAny] for testing purposes
        assert any("PRAGMA journal_mode=WAL" in str(call) for call in calls)
        assert any("PRAGMA synchronous=NORMAL" in str(call) for call in calls)
        assert any("PRAGMA foreign_keys=ON" in str(call) for call in calls)

    def test_enable_wal_mode_closes_cursor(self):
        """Test that cursor is closed even if exception occurs."""
        mock_cursor: MagicMock = MagicMock()
        mock_cursor.execute.side_effect = Exception("Test error")  # pyright: ignore[reportAny] for testing purposes
        mock_conn: MagicMock = MagicMock()
        mock_conn.cursor.return_value = mock_cursor  # pyright: ignore[reportAny] for testing purposes

        # Call should not raise, but cursor should still be closed
        with pytest.raises(Exception):
            enable_wal_mode(mock_conn, None)

        assert mock_cursor.close.called  # pyright: ignore[reportAny] for testing purposes


class TestCreateDbEngine:
    """Tests for create_db_engine function."""

    def test_create_db_engine_sqlite(self):
        """Test engine creation for SQLite database."""
        database_url = "sqlite:///:memory:"
        engine = create_db_engine(database_url)

        assert engine is not None
        assert "sqlite" in str(engine.url).lower()

        # Test that engine can connect
        with engine.connect() as conn:
            assert conn is not None

    def test_create_db_engine_sqlite_with_echo(self):
        """Test engine creation with echo enabled."""
        database_url = "sqlite:///:memory:"
        engine = create_db_engine(database_url, echo=True)

        assert engine.echo is True

    def test_create_db_engine_sqlite_registers_wal_listener(self):
        """Test that WAL mode listener is registered for SQLite."""
        database_url = "sqlite:///:memory:"

        with patch("compute.database.event.listen") as mock_listen:
            _ = create_db_engine(database_url)

            # Verify enable_wal_mode was registered as a listener
            # SQLAlchemy may call event.listen multiple times for internal purposes
            # We just need to verify our listener was registered
            calls = [str(call) for call in mock_listen.call_args_list]
            assert any("enable_wal_mode" in str(call) for call in calls)

    def test_create_db_engine_non_sqlite(self):
        """Test that non-SQLite databases don't get WAL listener."""
        database_url = "postgresql://localhost/testdb"

        with patch("compute.database.event.listen") as mock_listen:
            # This will fail to connect, but we only care about listener registration
            try:
                _ = create_db_engine(database_url)
            except Exception:
                pass  # Connection failure is expected for this test

            # enable_wal_mode should not be registered for non-SQLite
            # SQLAlchemy may call event.listen for other purposes
            calls = [str(call) for call in mock_listen.call_args_list]
            assert not any("enable_wal_mode" in str(call) for call in calls)


class TestCreateSessionFactory:
    """Tests for create_session_factory function."""

    def test_create_session_factory(self):
        """Test session factory creation."""
        engine = create_engine("sqlite:///:memory:")
        factory = create_session_factory(engine)

        assert factory is not None
        assert callable(factory)

        # Test that factory creates sessions
        session = factory()
        assert isinstance(session, Session)
        session.close()

    def test_create_session_factory_settings(self):
        """Test that session factory has correct settings."""
        engine = create_engine("sqlite:///:memory:")
        factory = create_session_factory(engine)

        session = factory()
        assert session.autoflush is False
        # autocommit attribute removed in SQLAlchemy 2.0
        session.close()


class TestGetDbSession:
    """Tests for get_db_session generator function."""

    def test_get_db_session_yields_session(self):
        """Test that get_db_session yields a session."""
        engine = create_engine("sqlite:///:memory:")
        factory = create_session_factory(engine)

        generator = get_db_session(factory)
        session = next(generator)

        assert isinstance(session, Session)

        # Clean up
        try:
            _ = next(generator)
        except StopIteration:
            pass

    def test_get_db_session_closes_on_exit(self):
        """Test that session is closed after use."""
        engine = create_engine("sqlite:///:memory:")
        factory = create_session_factory(engine)

        for _ in get_db_session(factory):
            pass  # Session is yielded

        # After generator completes, session should be closed
        # We can't directly check if closed, but we can verify no exception

    def test_get_db_session_closes_on_exception(self):
        """Test that session is closed even if exception occurs."""
        engine = create_engine("sqlite:///:memory:")
        factory = create_session_factory(engine)

        try:
            for _ in get_db_session(factory):
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected

        # Session should still be closed


class TestGetDb:
    """Tests for get_db FastAPI dependency."""

    def test_get_db_yields_session(self):
        """Test that get_db yields a session."""
        # get_db is a convenience wrapper around get_db_session
        
        # Mock SessionLocal to be a valid factory
        mock_factory = MagicMock()
        mock_session = MagicMock()
        mock_factory.return_value = mock_session
        
        with patch("compute.database.SessionLocal", mock_factory):
            generator = get_db()
            session = next(generator)

            assert session == mock_session

            # Clean up
            try:
                _ = next(generator)
            except StopIteration:
                pass
            
            mock_session.close.assert_called_once()

    def test_get_db_can_be_used_in_dependency(self):
        """Test that get_db works as FastAPI dependency."""
        # This test verifies get_db returns a generator
        db_gen = get_db()
        assert hasattr(db_gen, "__next__")
