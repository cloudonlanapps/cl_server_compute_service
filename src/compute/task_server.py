"""Task Server - Compute job and worker management service."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .database import get_db
from .plugins import create_compute_plugin_router
from .routes import router
from .schemas import RootResponse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ComputeServerConfig



def create_app(config: "ComputeServerConfig | None" = None) -> FastAPI:
    """Create and configure FastAPI application.
    
    Args:
        config: Service configuration. If None, derived from CLI/Env.
    """
    from .config import ComputeServerConfig
    from .database import check_tables_exist, init_db
    
    if config is None:
        try:
             config = ComputeServerConfig.get_config()
        except:
             raise ValueError("Failed to parse config from commandline")
        
    # Initialize DB (idempotent-ish, sets globals)
    init_db(config)
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Lifespan event handler for startup and shutdown."""
        from cl_ml_tools import MQTTBroadcaster, NoOpBroadcaster, get_broadcaster
        from loguru import logger
        from . import database
        
        # Inject config if not present (though create_app should ensure it)
        if not hasattr(app.state, "config"):
             app.state.config = config
             
        # Initialize MQTT Broadcaster
        logger.info(f"Initializing MQTT broadcaster at {config.mqtt_url}")
        broadcaster = get_broadcaster(url=config.mqtt_url)
        
        if not isinstance(broadcaster, MQTTBroadcaster):
            error_msg = "MQTT broadcaster required but returned NoOpBroadcaster or invalid type."
            logger.critical(error_msg)
            # Raise RuntimeError to stop Uvicorn startup
            raise RuntimeError(error_msg)
            
        app.state.broadcaster = broadcaster
        
        # Inject broadcaster into JobRepositoryService (late binding)
        if hasattr(app.state, "repository_adapter"):
            app.state.repository_adapter.set_broadcaster(broadcaster)
             
        # Initialize CapabilityManager singleton
        from .capability_manager import initialize_capability_manager
        initialize_capability_manager(config, broadcaster)
        
        # Startup: validate database tables exist
        check_tables_exist()

        yield
        
        # Shutdown: cleanup capability manager and broadcaster
        from .capability_manager import close_capability_manager
        close_capability_manager()
        
        # Disconnect broadcaster
        try:
            if broadcaster:
                logger.info("Disconnecting MQTT broadcaster...")
                broadcaster.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting broadcaster: {e}")
            
        # Dispose database connection
        try:
             if database.engine:
                 logger.info("Disposing database connection...")
                 database.engine.dispose()
        except Exception as e:
             logger.error(f"Error disposing database engine: {e}")

    app = FastAPI(title="Task Server", version="v1", lifespan=lifespan)
    app.state.config = config

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
        from .config_service import ServerPrefService

        config_service = ServerPrefService(db)
        auth_enabled = config_service.get_auth_enabled()
        guest_mode = "off" if auth_enabled else "on"

        return RootResponse(
            status="healthy",
            service="Task Server",
            version="v1",
            guestMode=guest_mode,
        )

    # Include job management routes
    app.include_router(router)

    # Create and include plugin router for compute tasks
    # Now we pass config to it
    plugin_router, repository_adapter = create_compute_plugin_router(config)
    app.include_router(plugin_router)
    
    # Store repository adapter for late binding of broadcaster
    app.state.repository_adapter = repository_adapter
    
    return app

# Global app instance for uvicorn import string compatibility
# This will use defaults (CLI args/Env) to initialize config
# If strictly no defaults allowed and env missing, this might fail at import time, 
# which is acceptable for strict mode.
try:
    app = create_app(None)
except Exception as e:
    # Allow import to succeed even if config fails (e.g. during pydoc or tests)
    # But uvicorn run would fail
    # We print error but create a dummy app to avoid import error?
    # No, better to let it fail if run directly.
    # checking if main
    pass
