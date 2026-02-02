from typing import TYPE_CHECKING
from cl_ml_tools import create_master_router

from . import database
from .auth import require_permission
from .repository import JobRepositoryService
from .storage import JobStorageService

if TYPE_CHECKING:
    from .config import ComputeConfig


def create_compute_plugin_router(config: "ComputeConfig"):
    """Create router with all registered compute plugins.

    Args:
        config: Compute service configuration

    Returns:
        tuple: (plugin_router, repository_adapter) for cleanup
    """
    # Create adapter instances
    repository_adapter = JobRepositoryService(database.SessionLocal, config)
    
    if not config.compute_storage_dir:
        raise ValueError("Compute storage directory not configured")
        
    job_storage_service = JobStorageService(base_dir=config.compute_storage_dir)

    # Create and mount plugin router
    # FastAPI dependency type doesn't match cl_ml_tools expectation, but works at runtime
    plugin_router = create_master_router(
        repository=repository_adapter,
        file_storage=job_storage_service,
        get_current_user=require_permission("ai_inference_support"),  # pyright: ignore[reportArgumentType]
    )

    return plugin_router, repository_adapter  # Return adapter for shutdown
