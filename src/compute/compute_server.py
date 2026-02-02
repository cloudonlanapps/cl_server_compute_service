# src/compute/compute_server.py
from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from loguru import logger


class Args(Namespace):
    host: str
    port: int
    debug: bool
    reload: bool
    log_level: str
    public_key_path: str
    auth_disabled: bool
    mqtt_url: str | None  # MQTT URL for broadcasting

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8002,
        debug: bool = False,
        reload: bool = False,
        log_level: str = "info",
        public_key_path: str = "",
        auth_disabled: bool = False,
        mqtt_url: str | None = "mqtt://localhost:1883",  # Default only in CLI
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.debug = debug
        self.reload = reload
        self.log_level = log_level
        self.public_key_path = public_key_path
        self.auth_disabled = auth_disabled
        self.mqtt_url = mqtt_url


def main() -> int:
    parser = ArgumentParser(prog="compute-server")
    _ = parser.add_argument(
        "--port", "-p", type=int, default=8002
    )
    _ = parser.add_argument("--host", default="0.0.0.0")
    _ = parser.add_argument(
        "--reload", action="store_true", help="Enable uvicorn reload (dev)"
    )
    _ = parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode"
    )
    _ = parser.add_argument(
        "--public-key-path",
        default="",
        help="Path to public key for JWT validation",
    )
    _ = parser.add_argument(
        "--no-auth",
        action="store_true",
        dest="auth_disabled",
        help="Disable authentication checks",
    )
    _ = parser.add_argument(
        "--mqtt-url",
        type=str,
        default="mqtt://localhost:1883",
        help=(
            "MQTT broker URL (e.g., mqtt://192.168.0.105:1883). "
            "Set to empty string to disable MQTT broadcasting."
        ),
    )

    args = parser.parse_args(namespace=Args())

    # Handle empty string as None (disables MQTT)
    if args.mqtt_url == "":
        args.mqtt_url = None

    # Ensure CL_SERVER_DIR exists
    # This handles the strict env check internally
    try:
        from .utils import ensure_cl_server_dir
        ensure_cl_server_dir(create_if_missing=True)
    except SystemExit:
        return 1
    
    # Initialize Config
    
    # Initialize Config
    from .config import ComputeConfig
    config = ComputeConfig.from_cli_args(args)
    
    # Initialize Database
    from . import database
    database.init_db(config)

    # Import uvicorn
    import uvicorn
    
    # Create app using factory and inject config
    from .task_server import create_app
    app = create_app(config)

    logger.info(f"Starting compute server on {args.host}:{args.port}")
    logger.info(f"Database: {config.database_url}")
    logger.info(f"Auth disabled: {config.auth_disabled}")
    logger.info(f"MQTT URL: {config.mqtt_url or 'disabled'}")

    # Start server (blocks)
    try:
        # Note: Passing the app object disables 'reload' support in standard uvicorn usage.
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level=args.log_level,
        )
    except Exception as exc:
        logger.error(f"Error starting service: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
