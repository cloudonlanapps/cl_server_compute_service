# src/compute/compute_server.py
from __future__ import annotations

from loguru import logger
from .config import ComputeServerConfig

def main() -> int:
    # Initialize Config via Singleton
    try:
        config = ComputeServerConfig.get_config()
    except SystemExit:
        # ArgumentParser raises SystemExit on --help or error
        return 1
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1

    # Initialize Database
    from . import database
    database.init_db(config)

    # Import uvicorn
    import uvicorn
    
    # Create app using factory and inject config
    from .task_server import create_app
    app = create_app(config)

    logger.info(f"Starting compute server on {config.host}:{config.port}")
    logger.info(f"Database: {config.database_url}")
    logger.info(f"Auth disabled: {config.auth_disabled}")

    # Start server (blocks)
    try:
        # Note: Passing the app object disables 'reload' support in standard uvicorn usage.
        uvicorn.run(
            app,
            host=config.host,
            port=config.port,
            log_level=config.log_level.lower(),
        )
    except Exception as exc:
        logger.error(f"Error starting service: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
