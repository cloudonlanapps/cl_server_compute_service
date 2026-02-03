"""Compute job response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, RootModel

type JSONPrimitive = str | int | float | bool | None
type JSONValue = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
type JSONObject = dict[str, JSONValue]


class JobResponse(BaseModel):
    """Response schema for job information.

    Contains job status, parameters, and output with service-specific fields
    for timestamps and priority.
    """

    job_id: str = Field(..., description="Unique job identifier")
    task_type: str = Field(..., description="Type of task to execute")
    status: str = Field(..., description="Job status (queued, in_progress, completed, failed)")
    progress: int = Field(0, description="Progress percentage (0-100)")
    params: JSONObject = Field(default_factory=dict, description="Task parameters")
    task_output: JSONObject | None = Field(None, description="Task output/results")
    error_message: str | None = Field(None, description="Error message if job failed")

    priority: int = Field(5, description="Job priority (0-10)")
    created_at: int = Field(..., description="Job creation timestamp (milliseconds)")
    updated_at: int | None = Field(None, description="Job last update timestamp (milliseconds)")
    started_at: int | None = Field(None, description="Job start timestamp (milliseconds)")
    completed_at: int | None = Field(None, description="Job completion timestamp (milliseconds)")


class StorageInfo(BaseModel):
    """Response schema for storage information."""

    total_size: int = Field(..., description="Total storage usage in bytes")
    job_count: int = Field(..., description="Number of jobs stored")


class CleanupResult(BaseModel):
    """Response schema for cleanup operation results."""

    deleted_count: int = Field(..., description="Number of jobs deleted")
    freed_space: int = Field(..., description="Space freed in bytes")


class CapabilityStats(RootModel[dict[str, int]]):
    """Aggregated capability statistics.

    Mapping of capability names to counts (e.g. idle count or total worker count).
    """

    root: dict[str, int]


class WorkerCapabilitiesResponse(BaseModel):
    """Response schema for worker capabilities endpoint."""

    num_workers: int = Field(..., description="Total number of connected workers")
    capabilities: CapabilityStats = Field(..., description="Available capability counts")


class PrefResponse(BaseModel):
    """Response schema for configuration endpoints."""

    guest_mode: bool = Field(..., description="Whether guest mode is enabled (true = no authentication required)")
    updated_at: int | None = Field(None, description="Timestamp of last update (milliseconds)")
    updated_by: str | None = Field(None, description="User ID who last updated the config")


class RootResponse(BaseModel):
    """Response schema for root health check endpoint."""

    status: str = Field(..., description="Health status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    guestMode: str = Field(..., description="Guest mode status (on/off)")
