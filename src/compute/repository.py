"""Adapter implementations for cl_ml_tools protocols.

This module provides adapter classes that bridge the cl_ml_tools library
protocols (JobRepository and JobStorage) with the application's actual
implementations (SQLAlchemy database).

The adapters handle:
- Mapping between library JobRecord (Pydantic) and database Job model (SQLAlchemy)
- Automatic timestamp management
- Atomic job claiming with optimistic locking
- MQTT broadcasting of job progress updates
"""

import json
import time
from collections.abc import Sequence
from typing import override

# Library protocols and schemas (Pydantic models)
from cl_ml_tools import (
    JobRecord,
    JobRecordUpdate,
    JobRepository,
    JobStatus,
    MQTTBroadcaster,
    NoOpBroadcaster,
    get_broadcaster,
)
from loguru import logger
from pydantic import JsonValue
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

# Application models (SQLAlchemy)
from .job_translator import db_job_to_job_record
from .models import Job
from .config import ComputeConfig


class JobRepositoryService(JobRepository):
    """SQLAlchemy implementation of JobRepository protocol.

    This adapter bridges the cl_ml_tools JobRepository protocol with
    SQLAlchemy database operations. It handles:

    - Mapping Pydantic JobRecord ↔ SQLAlchemy Job model
    - Timestamp management (created_at, started_at, completed_at)
    - Retry logic fields (retry_count, max_retries)
    - User tracking (created_by)
    - Atomic job claiming using optimistic locking
    """

    def __init__(self, session_factory: sessionmaker[Session], config: ComputeConfig):
        """Initialize repository with session factory and MQTT broadcaster.

        Args:
            session_factory: SQLAlchemy session factory (sessionmaker)
            config: ComputeConfig instance for MQTT settings
        """
        self.session_factory: sessionmaker[Session] = session_factory
        self.config = config

        # Setup broadcaster for job progress updates
        self.broadcaster: MQTTBroadcaster | NoOpBroadcaster | None = get_broadcaster(
            mqtt_url=config.mqtt_url,
        )
        logger.info(f"JobRepositoryService initialized with broadcaster: {self.broadcaster}")

    def _broadcast_progress(self, job_id: str, status: JobStatus, progress: int) -> None:
        """Broadcast job progress update via MQTT.

        Args:
            job_id: Unique job identifier
            status: Current job status
            progress: Progress percentage (0-100)
        """
        payload = {
            "job_id": job_id,
            "event_type": status.value,
            "timestamp": int(time.time() * 1000),
            "progress": progress,
        }

        if self.broadcaster:
            
            # Use configured topic prefix
            topic = self.config.mqtt_job_events_topic
            payload_str = json.dumps(payload)
            success = self.broadcaster.publish_event(topic=topic, payload=payload_str)
            if not success:
                logger.error(f"Failed to broadcast job event: topic={topic}, job_id={job_id}, status={status.value}")
            else:
                logger.info(f"Broadcasted job event: topic={topic}, job_id={job_id}, status={status.value}")
        else:
            logger.warning(f"No broadcaster available for job progress updates. Payload: {payload}")

    @override
    def add_job(
        self,
        job: JobRecord,
        created_by: str | None = None,
        priority: int | None = None,
    ) -> bool:
        """Save job to database.

        Converts JobRecord to database Job, adding:
        - created_at timestamp
        - retry_count = 0
        - max_retries = 3
        - created_by from parameter

        Args:
            job: Pydantic JobRecord to save
            created_by: Optional user identifier
            priority: Optional priority level

        Returns:
            True if job was saved successfully
        """
        session: Session
        with self.session_factory() as session:
            # Convert Pydantic JobRecord to SQLAlchemy Job
            db_job = Job(
                job_id=job.job_id,
                task_type=job.task_type,
                params=job.params,  # Pydantic model_dump() converts to dict
                status=job.status.value,  # Convert enum to string
                progress=job.progress,
                created_at=int(time.time() * 1000),  # Current timestamp in milliseconds
                output=job.output,  # Pydantic model_dump() if present
                error_message=job.error_message,
                priority=priority if priority is not None else 0,
                retry_count=0,
                max_retries=3,
                created_by=created_by,
            )

            session.add(db_job)
            session.commit()

            self._broadcast_progress(db_job.job_id, JobStatus(db_job.status), db_job.progress)

            return True

    @override
    def get_job(self, job_id: str) -> JobRecord | None:
        """Get job by ID.

        Args:
            job_id: Unique job identifier

        Returns:
            Pydantic JobRecord if found, None otherwise
        """
        with self.session_factory() as session:
            stmt = select(Job).where(Job.job_id == job_id)
            db_job = session.execute(stmt).scalar_one_or_none()

            if db_job:
                return db_job_to_job_record(db_job)
            return None

    @override
    def update_job(
        self,
        job_id: str,
        updates: JobRecordUpdate,
    ) -> bool:
        """Update job fields and broadcast progress to MQTT.

        Handles Pydantic JobRecordUpdate model:
        - Fields: status, progress, output, error_message
        - Auto-sets timestamps based on status changes
        - Broadcasts progress updates via MQTT

        Args:
            job_id: Unique job identifier
            updates: Pydantic JobRecordUpdate with fields to update

        Returns:
            True if job was updated, False if job not found
        """
        with self.session_factory() as session:
            # Build update values from Pydantic model
            update_values: dict[str, JsonValue] = updates.model_dump(exclude_none=True)

            status = update_values.get("status")
            if status is not None:
                job_status = JobStatus(status)
                update_values["status"] = job_status.value

                now_ms = int(time.time() * 1000)

                if job_status is JobStatus.processing:
                    stmt = select(Job.started_at).where(Job.job_id == job_id)
                    if session.execute(stmt).scalar_one_or_none() is None:
                        update_values["started_at"] = now_ms

                elif job_status in (JobStatus.completed, JobStatus.error):
                    update_values["completed_at"] = now_ms

            if not update_values:
                return False

            # Execute update
            stmt = (
                update(Job)
                .where(Job.job_id == job_id)
                .values(**update_values)
                .returning(Job)
            )
            # Execute and get the updated/latest object
            db_job = session.execute(stmt).scalar_one_or_none()
            session.commit()

            if db_job is not None:
                # Refresh to ensure we have any defaults/computed fields if any
                session.refresh(db_job)
                
                # Always broadcast after a successful update
                # We use the current state from DB to ensure we have both status and progress
                self._broadcast_progress(
                    db_job.job_id, 
                    JobStatus(db_job.status), 
                    db_job.progress
                )

            return db_job is not None

    @override
    def fetch_next_job(self, task_types: Sequence[str]) -> JobRecord | None:
        """Atomically find and claim the next queued job.

        Uses optimistic locking to prevent race conditions:
        1. Find job with status="queued" AND task_type in task_types
        2. Atomically update status to "processing" and set started_at
        3. Return the claimed job as Pydantic JobRecord

        The UPDATE ... WHERE query ensures atomicity - only one worker
        will successfully claim a specific job even if multiple workers
        query simultaneously.

        Args:
            task_types: Sequence of task types to process

        Returns:
            Pydantic JobRecord with status="processing" if found, None otherwise
        """
        if not task_types:
            return None

        with self.session_factory() as session:
            # Find next queued job with matching task type
            # Order by created_at to process oldest first
            stmt = (
                select(Job)
                .where(
                    Job.status == "queued",
                    Job.task_type.in_(task_types),
                )
                .order_by(Job.created_at)
                .limit(1)
            )

            db_job = session.execute(stmt).scalar_one_or_none()
            
            logger.info(f"fetch_next_job: task_types={task_types}, found_job={db_job.job_id if db_job else 'None'}")
            if db_job:
                 logger.info(f"Found job: {db_job.job_id} status={db_job.status} task_type={db_job.task_type}")

            if not db_job:
                return None

            # Atomically claim the job using optimistic locking
            # This UPDATE will only succeed if status is still "queued"
            current_time = int(time.time() * 1000)
            stmt = (
                update(Job)
                .where(
                    Job.job_id == db_job.job_id,
                    Job.status == "queued",  # Optimistic lock
                )
                .values(status="processing", started_at=current_time)
                .returning(Job)
            )

            db_job: Job | None = session.execute(stmt).scalar_one_or_none()
            session.commit()

            # Check if we successfully claimed the job
            if db_job is None:
                # Another worker claimed it first
                return None

            # Refresh the job object to get updated values
            session.refresh(db_job)
            self._broadcast_progress(db_job.job_id, JobStatus(db_job.status), db_job.progress)
            return db_job_to_job_record(db_job)

    @override
    def delete_job(self, job_id: str) -> bool:
        """Delete job from database.

        Args:
            job_id: Unique job identifier

        Returns:
            True if job was deleted, False if job not found
        """
        with self.session_factory() as session:
            stmt = select(Job).where(Job.job_id == job_id)
            db_job = session.execute(stmt).scalar_one_or_none()

            if db_job:
                session.delete(db_job)
                session.commit()
                return True

            return False
