"""Tests for service layer."""

import tempfile
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from compute.models import Base, Job
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from compute.schemas import CapabilityStats
from compute.service import CapabilityService, JobService
from compute.config import ComputeConfig


@pytest.fixture
def mock_config(temp_storage_dir: Path, mqtt_url: str) -> ComputeConfig:
    """Create mock configuration."""
    config = MagicMock(spec=ComputeConfig)
    config.compute_storage_dir = str(temp_storage_dir)
    config.mqtt_url = mqtt_url
    return config


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """Create test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def temp_storage_dir() -> Generator[Path, None, None]:
    """Create temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestJobService:
    """Tests for JobService."""

    def test_job_service_init(self, test_db: Session, mock_config: ComputeConfig):
        """Test JobService initialization."""
        service = JobService(test_db, mock_config)

        assert service.db == test_db
        assert service.config == mock_config
        assert service.repository is not None
        assert service.file_storage is not None
        assert service.storage_base is not None

    def test_get_job_success(self, test_db: Session, mock_config: ComputeConfig):
        """Test getting a job that exists."""
        # Create test job in database
        job = Job(
            job_id="test-job-1",
            task_type="test_task",
            status="queued",
            progress=0,
            params={"key": "value"},
            output={},
            created_at=1234567890000,
            priority=5,
        )
        test_db.add(job)
        test_db.commit()

        # Get job using service
        # Get job using service
        service = JobService(test_db, mock_config)
        result = service.get_job("test-job-1")

        assert result.job_id == "test-job-1"
        assert result.task_type == "test_task"
        assert result.status == "queued"
        assert result.params == {"key": "value"}

    def test_get_job_not_found(self, test_db: Session, mock_config: ComputeConfig):
        """Test getting a job that doesn't exist."""
        service = JobService(test_db, mock_config)

        with pytest.raises(HTTPException) as exc_info:
            _ = service.get_job("nonexistent-job")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_get_job_with_all_fields(self, test_db: Session, mock_config: ComputeConfig):
        """Test getting a job with all fields populated."""
        job = Job(
            job_id="test-job-2",
            task_type="image_resize",
            status="completed",
            progress=100,
            params={"width": 800},
            output={"result": "success"},
            created_at=1234567890000,
            started_at=1234567890500,
            completed_at=1234567891000,
            priority=7,
        )
        test_db.add(job)
        test_db.commit()

        service = JobService(test_db, mock_config)
        result = service.get_job("test-job-2")

        assert result.progress == 100
        assert result.status == "completed"
        assert result.started_at == 1234567890500
        assert result.completed_at == 1234567891000
        assert result.priority == 7

    def test_delete_job_success(self, test_db: Session, mock_config: ComputeConfig):
        """Test deleting a job."""
        # Create test job
        job = Job(
            job_id="test-job-3",
            task_type="test_task",
            status="completed",
            progress=100,
            params={},
            output={},
            created_at=1234567890000,
            priority=5,
        )
        test_db.add(job)
        test_db.commit()

        service = JobService(test_db, mock_config)

        # Mock repository and file storage
        with patch.object(service.repository, "get_job", return_value=job):
            with patch.object(service.repository, "delete_job", return_value=None) as mock_delete:
                with patch.object(service.file_storage, "remove", return_value=None) as mock_remove:
                    service.delete_job("test-job-3")

                    # Verify repository.delete_job was called
                    mock_delete.assert_called_once_with("test-job-3")
                    mock_remove.assert_called_once_with("test-job-3")

    def test_delete_job_not_found(self, test_db: Session, mock_config: ComputeConfig):
        """Test deleting a job that doesn't exist."""
        service = JobService(test_db, mock_config)

        with patch.object(service.repository, "get_job", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                service.delete_job("nonexistent-job")

            assert exc_info.value.status_code == 404

    def test_get_storage_size_empty(self, test_db: Session, mock_config: ComputeConfig):
        """Test get_storage_size with no jobs."""
        service = JobService(test_db, mock_config)
        result = service.get_storage_size()

        assert result.total_size == 0
        assert result.job_count == 0

    def test_get_storage_size_with_jobs(self, test_db: Session, mock_config: ComputeConfig, temp_storage_dir: Path):
        """Test get_storage_size with jobs."""
        # Create job directories with files
        jobs_dir = temp_storage_dir / "jobs"
        jobs_dir.mkdir()

        job1_dir = jobs_dir / "job-1"
        job1_dir.mkdir()
        _ = (job1_dir / "file1.txt").write_text("test content 1")

        job2_dir = jobs_dir / "job-2"
        job2_dir.mkdir()
        _ = (job2_dir / "file2.txt").write_text("test content 2")

        service = JobService(test_db, mock_config)
        result = service.get_storage_size()

        assert result.total_size > 0
        assert result.job_count == 2

    def test_cleanup_old_jobs_no_old_jobs(self, test_db: Session, mock_config: ComputeConfig):
        """Test cleanup when no old jobs exist."""
        service = JobService(test_db, mock_config)
        result = service.cleanup_old_jobs(days=7)

        assert result.deleted_count == 0
        assert result.freed_space == 0

    def test_cleanup_old_jobs_with_old_jobs(self, test_db: Session, mock_config: ComputeConfig, temp_storage_dir: Path):
        """Test cleanup with old jobs."""
        import time

        # Create job directory with old modification time
        jobs_dir = temp_storage_dir / "jobs"
        jobs_dir.mkdir()

        old_job_dir = jobs_dir / "old-job"
        old_job_dir.mkdir()
        test_file = old_job_dir / "file.txt"
        _ = test_file.write_text("test content")

        # Set old modification time (8 days ago)
        old_time = time.time() - (8 * 24 * 60 * 60)
        import os

        os.utime(old_job_dir, (old_time, old_time))

        # Create old job in database
        old_timestamp = int((datetime.now(UTC).timestamp() - (8 * 24 * 60 * 60)) * 1000)
        old_job = Job(
            job_id="old-job",
            task_type="test_task",
            status="completed",
            progress=100,
            params={},
            output={},
            created_at=old_timestamp,
            priority=5,
        )
        test_db.add(old_job)
        test_db.commit()

        service = JobService(test_db, mock_config)

        with patch.object(service.repository, "delete_job", return_value=None):
            with patch.object(service.file_storage, "remove", return_value=None):
                result = service.cleanup_old_jobs(days=7)

                assert result.deleted_count >= 0
                # File should have been counted
                assert result.freed_space > 0


class TestCapabilityService:
    """Tests for CapabilityService."""

    def test_capability_service_init(self, test_db: Session):
        """Test CapabilityService initialization."""
        service = CapabilityService(test_db)

        assert service.db == test_db

    def test_get_available_capabilities_success(self, test_db: Session):
        """Test getting available capabilities."""
        mock_manager = MagicMock()
        mock_manager.get_cached_capabilities.return_value = CapabilityStats(  # pyright: ignore[reportAny] ignore mock types for testing purposes
            root={
                "image_resize": 2,
                "image_conversion": 1,
            }
        )

        with patch("compute.capability_manager.get_capability_manager", return_value=mock_manager):
            service = CapabilityService(test_db)
            result = service.get_available_capabilities()

            assert result.root == {"image_resize": 2, "image_conversion": 1}
            mock_manager.get_cached_capabilities.assert_called_once()  # pyright: ignore[reportAny] ignore mock types for testing purposes

    def test_get_available_capabilities_error(self, test_db: Session):
        """Test get_available_capabilities when error occurs."""
        with patch(
            "compute.capability_manager.get_capability_manager",
            side_effect=Exception("Test error"),
        ):
            service = CapabilityService(test_db)
            result = service.get_available_capabilities()

            # Should return empty dict wrapped in CapabilityStats on error
            assert result.root == {}

    def test_get_worker_count_success(self, test_db: Session):
        """Test getting worker count."""
        mock_manager = MagicMock()
        mock_manager.capabilities_cache = {
            "worker-1": MagicMock(),
            "worker-2": MagicMock(),
            "worker-3": MagicMock(),
        }

        with patch("compute.capability_manager.get_capability_manager", return_value=mock_manager):
            service = CapabilityService(test_db)
            result = service.get_worker_count()

            assert result == 3

    def test_get_worker_count_error(self, test_db: Session):
        """Test get_worker_count when error occurs."""
        with patch(
            "compute.capability_manager.get_capability_manager",
            side_effect=Exception("Test error"),
        ):
            service = CapabilityService(test_db)
            result = service.get_worker_count()

            # Should return 0 on error
            assert result == 0

    def test_get_worker_count_no_workers(self, test_db: Session):
        """Test get_worker_count with no workers."""
        mock_manager = MagicMock()
        mock_manager.capabilities_cache = {}

        with patch("compute.capability_manager.get_capability_manager", return_value=mock_manager):
            service = CapabilityService(test_db)
            result = service.get_worker_count()

            assert result == 0
