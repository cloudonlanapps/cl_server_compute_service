import uvicorn
from loguru import logger

from . import database
from .config import ComputeServerConfig
from .task_server import create_app


def main() -> int:
    # Initialize Config
    config = ComputeServerConfig.from_args()
    
    # Initialize Database
    database.init_db(config)

    # Create app using factory and inject config
    app = create_app(config)

    logger.info(f"Starting compute server on {config.host}:{config.port}")
    logger.info(f"Database: {config.database_url}")
    logger.info(f"Auth disabled: {config.auth_disabled}")
    logger.info(f"MQTT URL: {config.mqtt_url or 'disabled'}")

    # Start server (blocks)
    try:
        # Note: Passing the app object disables 'reload' support in standard uvicorn usage.
        uvicorn.run(
            app,
            host=config.host,
            port=config.port,
            log_level=config.log_level,
        )
    except Exception as exc:
        logger.error(f"Error starting service: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
