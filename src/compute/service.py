"""Compute job services."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Job
from .schemas import CapabilityStats, CleanupResult, JobResponse, StorageInfo
from .repository import JobRepositoryService
from .storage import JobStorageService

if TYPE_CHECKING:
    from .config import ComputeServerConfig


from cl_ml_tools import MQTTBroadcaster

# ... (imports)

class JobService:
    """Service layer for job management."""

    def __init__(self, db: Session, config: ComputeServerConfig, broadcaster: MQTTBroadcaster | None = None):
        """Initialize the job service.

        Args:
            db: SQLAlchemy database session
            config: Compute service configuration
            broadcaster: Optional MQTT broadcaster
        """
        self.db: Session = db
        self.config = config
        
        # Create repository adapter
        self.repository: JobRepositoryService = JobRepositoryService(SessionLocal, config, broadcaster)
        
        # Use compute_storage_dir for job files (organized per job)
        if not config.compute_storage_dir:
             raise ValueError("Compute storage directory not configured")
             
        self.file_storage: JobStorageService = JobStorageService(
            base_dir=config.compute_storage_dir
        )
        self.storage_base: Path = Path(config.compute_storage_dir)

    def get_job(self, job_id: str) -> JobResponse:
        """Get job status and results.

        Args:
             job_id: Unique job identifier

         Returns:
             JobResponse with job details

         Raises:
             ValueError: If job not found
        """
        # Get additional metadata from database
        db_job = self.db.query(Job).filter_by(job_id=job_id).first()
        if not db_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
            )

        return JobResponse(
            job_id=db_job.job_id,
            task_type=db_job.task_type,
            status=db_job.status,
            progress=db_job.progress,
            params=db_job.params,
            task_output=db_job.output,
            created_at=db_job.created_at,
            updated_at=db_job.created_at,
            started_at=db_job.started_at,
            completed_at=db_job.completed_at,
            error_message=(
                db_job.error_message if hasattr(db_job, "error_message") else None
            ),
            priority=db_job.priority,
        )

    def delete_job(self, job_id: str) -> None:
        """Delete job and all associated files.

        Args:
            job_id: Unique job identifier

        Raises:
            HTTPException: If job not found
        """
        # Check job exists using repository
        library_job = self.repository.get_job(job_id)
        if not library_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
            )

        # Delete job directory using JobStorage protocol method
        _ = self.file_storage.remove(job_id)

        # Use repository to delete job (handles QueueEntry cascade)
        _ = self.repository.delete_job(job_id)

    def get_job_file(self, job_id: str, file_path: str) -> Path:
        """Get file from job's output directory.

        Args:
            job_id: Unique job identifier
            file_path: Relative file path within job directory

        Returns:
            Absolute path to the requested file

        Raises:
            HTTPException: If job not found, file not found, or path traversal detected
        """
        # Verify job exists
        library_job = self.repository.get_job(job_id)
        if not library_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Job {job_id} not found"
            )

        # Get job directory
        job_dir = self.storage_base / "jobs" / job_id

        if not job_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job directory not found for job {job_id}",
            )

        # Resolve requested file path (prevent directory traversal)
        try:
            requested_file = (job_dir / file_path).resolve()
        except (ValueError, OSError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file path: {e}",
            )

        # Security check: ensure resolved path is within job directory
        try:
            _ = requested_file.relative_to(job_dir.resolve())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: path traversal detected",
            )

        # Check file exists
        if not requested_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {file_path}",
            )

        # Check it's a file, not a directory
        if not requested_file.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Path is not a file: {file_path}",
            )

        return requested_file

    def get_storage_size(self) -> StorageInfo:
        """Get total storage usage for all jobs.

        Returns:
            StorageInfo with storage details
        """
        # Calculate storage size directly
        jobs_dir = self.storage_base / "jobs"
        total_size = 0
        job_count = 0

        if jobs_dir.exists():
            for job_dir in jobs_dir.iterdir():
                if job_dir.is_dir():
                    job_count += 1
                    for file_path in job_dir.rglob("*"):
                        if file_path.is_file():
                            total_size += file_path.stat().st_size

        storage_info = {
            "total_size": total_size,
            "job_count": job_count,
        }
        return StorageInfo(**storage_info)

    def cleanup_old_jobs(self, days: int) -> CleanupResult:
        """Clean up jobs older than specified number of days.

        Args:
            days: Number of days threshold

        Returns:
            CleanupResult with cleanup details
        """
        import time

        # Calculate cleanup info directly
        jobs_dir = self.storage_base / "jobs"
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)
        deleted_count = 0
        freed_space = 0

        if jobs_dir.exists():
            for job_dir in jobs_dir.iterdir():
                if job_dir.is_dir():
                    # Check modification time
                    dir_mtime = job_dir.stat().st_mtime
                    if dir_mtime < cutoff_time:
                        # Calculate size before deletion
                        for file_path in job_dir.rglob("*"):
                            if file_path.is_file():
                                freed_space += file_path.stat().st_size

                        # Delete job using JobStorage protocol method
                        _ = self.file_storage.remove(job_dir.name)
                        deleted_count += 1

        # Remove cleaned up jobs from database using repository
        current_time_ms = int(datetime.now(UTC).timestamp() * 1000)
        cutoff_time_ms = current_time_ms - (days * 24 * 60 * 60 * 1000)

        old_jobs = self.db.query(Job).filter(Job.created_at < cutoff_time_ms).all()
        for job in old_jobs:
            # Use repository to delete (handles QueueEntry cascade)
            _ = self.repository.delete_job(job.job_id)

        cleanup_info = {
            "deleted_count": deleted_count,
            "freed_space": freed_space,
        }
        return CleanupResult(**cleanup_info)


class CapabilityService:
    """Service layer for worker capability management."""

    def __init__(self, db: Session):
        """Initialize capability service.

        Args:
            db: SQLAlchemy database session
        """
        self.db: Session = db

    def get_available_capabilities(self) -> CapabilityStats:
        """Get aggregated available worker capabilities.

        Returns:
            Dict mapping capability names to available idle count
            Example: {"image_resize": 2, "image_conversion": 1}
        """
        try:
            from .capability_manager import get_capability_manager

            manager = get_capability_manager()
            return manager.get_cached_capabilities()
        except Exception as e:

            logger.error(f"Error retrieving worker capabilities: {e}")
            return CapabilityStats(root={})

    def get_worker_count(self) -> int:
        """Get total number of connected workers.

        Returns:
            Number of unique workers in the capability cache
        """
        try:
            from .capability_manager import get_capability_manager

            manager = get_capability_manager()
            return len(manager.capabilities_cache)
        except Exception as e:

            logger.error(f"Error retrieving worker count: {e}")
            return 0
