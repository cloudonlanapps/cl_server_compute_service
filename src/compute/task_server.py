"""Task Server - Compute job and worker management service."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .plugins import create_compute_plugin_router
from .routes import router
from .schemas import RootResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    from .config import ComputeConfig
    from .database import check_tables_exist, init_db

    # Initialize configuration and database
    # Check if config is already injected (e.g. by compute_server.py)
    if not hasattr(app.state, "config"):
        # Note: In production, CLI args are passed; in tests, we rely on mocks or pytest args
        # When running simply via uvicorn/deployment without compute_server wrapper, use defaults/env
        config = ComputeConfig.from_cli_args(None)
        init_db(config)
        app.state.config = config
    
    _ = app
    # Startup: validate database tables exist
    check_tables_exist()

    yield
    # Shutdown: cleanup capability manager
    from .capability_manager import close_capability_manager

    close_capability_manager()


app = FastAPI(title="Task Server", version="v1", lifespan=lifespan)

# Include job management routes
app.include_router(router)

# Create and include plugin router for compute tasks
plugin_router, repository_adapter = create_compute_plugin_router()
app.include_router(plugin_router)


@app.exception_handler(HTTPException)
async def validation_exception_handler(_request: Request, exc: HTTPException):
    """
    Preserve the default FastAPI HTTPException handling shape so callers
    can rely on the same error response structure.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.get(
    "/",
    summary="Health Check",
    description="Returns service health status",
    response_model=RootResponse,
    operation_id="root_get",
)
async def root(db: Session = Depends(get_db)):
    from .config_service import ConfigService

    config_service = ConfigService(db)
    auth_enabled = config_service.get_auth_enabled()
    guest_mode = "off" if auth_enabled else "on"

    return RootResponse(
        status="healthy",
        service="Task Server",
        version="v1",
        guestMode=guest_mode,
    )
