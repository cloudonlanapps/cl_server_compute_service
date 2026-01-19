"""Task and job models.

Defines local models for Job, QueueEntry, and ServiceConfig, replacing shared dependencies.
"""

from __future__ import annotations

from typing import TypeAlias, override

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


# Type aliases for JSON fields
JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


class Job(Base):
    """Job model storing compute job metadata, status, and results.

    This model is shared between:
    - store_service: Creates and manages jobs
    - compute_worker: Claims and processes jobs

    Both services access the same database table.
    """

    __tablename__ = "jobs"  # pyright: ignore[reportUnannotatedClassAttribute]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)

    # JSON fields for params and output (dict, not string)
    params: Mapped[JSONObject] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    output: Mapped[JSONObject | None] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    created_by: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    updated_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    @override
    def __repr__(self) -> str:
        return f"<Job(job_id={self.job_id}, task_type={self.task_type}, status={self.status})>"


class QueueEntry(Base):
    """Priority queue entry for job scheduling.

    Used by store_service to manage job priority.
    """

    __tablename__ = "queue_entries"  # pyright: ignore[reportUnannotatedClassAttribute]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    enqueued_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    @override
    def __repr__(self):
        return f"<QueueEntry(job_id={self.job_id}, priority={self.priority})>"


class ServiceConfig(Base):
    """SQLAlchemy model for service configuration."""

    __tablename__ = "service_config"  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key
    key: Mapped[str] = mapped_column(String, primary_key=True)

    # Configuration value (stored as string, parsed as needed)
    value: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)

    @override
    def __repr__(self) -> str:
        return f"<ServiceConfig(key={self.key}, value={self.value})>"


__all__ = ["Base", "Job", "QueueEntry", "ServiceConfig"]
