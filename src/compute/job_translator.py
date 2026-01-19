"""Job model shared between store service and compute worker."""


# -------------------------------------------------------------------------
# Pydantic Conversion Helpers
# -------------------------------------------------------------------------

from cl_ml_tools import JobRecord

from .models import Job


def db_job_to_job_record(db_job: Job) -> "JobRecord":
    """Convert SQLAlchemy Job to Pydantic JobRecord.

    Returns:
        Pydantic JobRecord with core job fields
    """
    from cl_ml_tools.common.schema_job_record import JobRecord, JobStatus

    return JobRecord(
        job_id=db_job.job_id,
        task_type=db_job.task_type,
        params=db_job.params,
        output=db_job.output,
        status=JobStatus(db_job.status),
        progress=db_job.progress,
        error_message=db_job.error_message,
        # created_at=db_job.created_at, # JobRecord might not have created_at in some versions, check shared_db
    )


def job_record_to_db_job(
    job_record: "JobRecord",
    *,
    created_by: str | None = None,
    priority: int | None = None,
) -> "Job":
    """Create SQLAlchemy Job from Pydantic JobRecord.

    Args:
        job_record: Pydantic JobRecord
        created_by: Optional user identifier
        priority: Optional priority level

    Returns:
        SQLAlchemy Job instance (not persisted)
    """
    import time

    return Job(
        job_id=job_record.job_id,
        task_type=job_record.task_type,
        params=job_record.params,
        status=job_record.status.value,
        progress=job_record.progress,
        output=job_record.output,
        error_message=job_record.error_message,
        created_at=int(time.time() * 1000),
        priority=priority or 0,
        retry_count=0,
        max_retries=3,
        created_by=created_by,
    )
