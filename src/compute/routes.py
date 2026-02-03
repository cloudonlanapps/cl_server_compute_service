"""Compute job management routes."""

from fastapi import APIRouter, Depends, Form, Path, Query, status, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import TYPE_CHECKING

from .auth import UserPayload, require_admin, require_permission
from .database import get_db
from .schemas import (
    CleanupResult,
    ConfigResponse,
    JobResponse,
    StorageInfo,
    WorkerCapabilitiesResponse,
)
from cl_ml_tools import MQTTBroadcaster
from .dependencies import get_mqtt_broadcaster
from .service import CapabilityService, JobService

if TYPE_CHECKING:
    from .config import ComputeConfig

router = APIRouter()

def get_config(request: Request) -> "ComputeConfig":
    """Get service configuration from app state."""
    return request.app.state.config

@router.get(
    "/jobs/{job_id}",
    tags=["job"],
    summary="Get Job Status",
    description="Get job status and results.",
    operation_id="get_job",
    responses={200: {"model": JobResponse, "description": "Job found"}},
)
async def get_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    config: "ComputeConfig" = Depends(get_config),
    broadcaster: MQTTBroadcaster | None = Depends(get_mqtt_broadcaster),
    user: UserPayload | None = Depends(require_permission("ai_inference_support")),
) -> JobResponse:
    """Get job status and results."""
    _ = user
    job_service = JobService(db, config, broadcaster)
    return job_service.get_job(job_id)


@router.delete(
    "/jobs/{job_id}",
    tags=["job"],
    summary="Delete Job",
    description="Delete job and all associated files.",
    operation_id="delete_job",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    config: "ComputeConfig" = Depends(get_config),
    broadcaster: MQTTBroadcaster | None = Depends(get_mqtt_broadcaster),
    user: UserPayload | None = Depends(require_permission("ai_inference_support")),
):
    """Delete job and all associated files."""
    _ = user
    job_service = JobService(db, config, broadcaster)
    job_service.delete_job(job_id)
    # No return statement - FastAPI will return 204 automatically


@router.get(
    "/jobs/{job_id}/files/{file_path:path}",
    tags=["job"],
    summary="Download Job Output File",
    description="Download a file from job's output directory using relative path from task_output.",
    operation_id="get_job_file",
    response_class=FileResponse,
)
async def get_job_file(
    job_id: str = Path(..., title="Job ID"),
    file_path: str = Path(..., title="Relative file path within job directory"),
    db: Session = Depends(get_db),
    config: "ComputeConfig" = Depends(get_config),
    broadcaster: MQTTBroadcaster | None = Depends(get_mqtt_broadcaster),
    user: UserPayload | None = Depends(require_permission("ai_inference_support")),
) -> FileResponse:
    """Download file from job's output directory.

    Args:
        job_id: Job UUID
        file_path: Relative file path from task_output (e.g., "output/thumbnail.jpg")
        db: Database session
        user: Authenticated user

    Returns:
        File content with appropriate Content-Type

    Raises:
        404: Job or file not found
        403: Path traversal attempt detected
        400: Invalid file path or path is a directory
    """
    _ = user
    job_service = JobService(db, config, broadcaster)
    file_absolute_path = job_service.get_job_file(job_id, file_path)

    # Return file with FileResponse (FastAPI automatically sets Content-Type)
    return FileResponse(
        path=file_absolute_path,
        filename=file_absolute_path.name,
        media_type="application/octet-stream",  # Let browser determine type
    )


@router.get(
    "/admin/jobs/storage/size",
    tags=["admin"],
    summary="Get Storage Size",
    description="Get total storage usage (admin only).",
    operation_id="get_storage_size",
    responses={200: {"model": StorageInfo, "description": "Storage information"}},
)
async def get_storage_size(
    db: Session = Depends(get_db),
    config: "ComputeConfig" = Depends(get_config),
    broadcaster: MQTTBroadcaster | None = Depends(get_mqtt_broadcaster),
    user: UserPayload | None = Depends(require_admin),
) -> StorageInfo:
    """Get total storage usage (admin only)."""
    _ = user
    job_service = JobService(db, config, broadcaster)
    return job_service.get_storage_size()


@router.delete(
    "/admin/jobs/cleanup",
    tags=["admin"],
    summary="Cleanup Old Jobs",
    description="Clean up jobs older than specified number of days (admin only).",
    operation_id="cleanup_old_jobs",
    responses={200: {"model": CleanupResult, "description": "Cleanup results"}},
)
async def cleanup_old_jobs(
    days: int = Query(7, ge=0, description="Delete jobs older than N days"),
    db: Session = Depends(get_db),
    config: "ComputeConfig" = Depends(get_config),
    broadcaster: MQTTBroadcaster | None = Depends(get_mqtt_broadcaster),
    user: UserPayload | None = Depends(require_admin),
) -> CleanupResult:
    """Clean up jobs older than specified number of days (admin only)."""
    _ = user
    job_service = JobService(db, config, broadcaster)
    return job_service.cleanup_old_jobs(days)


@router.get(
    "/capabilities",
    tags=["compute"],
    summary="Get Worker Capabilities",
    description="Returns available worker capabilities and their available counts",
    response_model=WorkerCapabilitiesResponse,
    operation_id="get_worker_capabilities",
)
async def get_worker_capabilities(
    db: Session = Depends(get_db),
) -> WorkerCapabilitiesResponse:
    """Get available worker capabilities and counts from connected workers.

    Returns a dictionary with:
    - num_workers: Total number of connected workers (0 if none available)
    - capabilities: Dictionary mapping capability names to available worker counts

    Example response:
    {
        "num_workers": 3,
        "capabilities": {
            "image_resize": 2,
            "image_conversion": 1
        }
    }
    """
    _ = db
    capability_service = CapabilityService(db)
    capabilities = capability_service.get_available_capabilities()
    num_workers = capability_service.get_worker_count()
    return WorkerCapabilitiesResponse(
        num_workers=num_workers,
        capabilities=capabilities,
    )


# Admin configuration endpoints
@router.get(
    "/admin/config",
    tags=["admin"],
    summary="Get Configuration",
    description="Get current service configuration. Requires admin access.",
    operation_id="get_config_admin_config_get",
    responses={200: {"model": ConfigResponse, "description": "Successful Response"}},
)
async def get_config(
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_admin),
) -> ConfigResponse:
    """Get current service configuration.

    Requires admin access.
    """
    _ = user
    from .config_service import ConfigService

    config_service = ConfigService(db)

    # Get config metadata
    metadata = config_service.get_config_metadata("auth_enabled")

    if metadata:
        value_str = str(metadata["value"]) if metadata["value"] is not None else "false"
        updated_at = metadata["updated_at"]
        updated_by = metadata["updated_by"]
        # Invert logic: auth_enabled=false means guest_mode=true
        auth_enabled = value_str.lower() == "true"
        return ConfigResponse(
            guest_mode=not auth_enabled,
            updated_at=int(updated_at)
            if updated_at is not None and not isinstance(updated_at, str)
            else None,
            updated_by=str(updated_by)
            if updated_by is not None and not isinstance(updated_by, int)
            else None,
        )

    # Default if not found: auth_enabled=false means guest_mode=true
    return ConfigResponse(guest_mode=True, updated_at=None, updated_by=None)


@router.put(
    "/admin/config/guest-mode",
    tags=["admin"],
    summary="Update Guest Mode Configuration",
    description="Toggle guest mode (authentication requirement). Requires admin access.",
    operation_id="update_guest_mode_admin_config_guest_mode_put",
    responses={200: {"description": "Successful Response"}},
)
async def update_guest_mode(
    guest_mode: bool = Form(..., title="Guest Mode"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_admin),
) -> dict[str, bool | str]:
    """Update guest mode configuration.

    Requires admin access. Changes are persistent and take effect immediately.
    guest_mode=true means no authentication required.
    guest_mode=false means authentication required.
    """
    from .config_service import ConfigService

    config_service = ConfigService(db)

    # Get user ID from JWT
    user_id = user.id if user else None

    # Invert logic: guest_mode=true means auth_enabled=false
    config_service.set_auth_enabled(not guest_mode, user_id)

    return {
        "guest_mode": guest_mode,
        "message": "Configuration updated successfully",
    }
