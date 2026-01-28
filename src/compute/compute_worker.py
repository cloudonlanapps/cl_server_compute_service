"""Compute worker CLI entry point.

This CLI:
- Parses command-line arguments
- Configures logging
- Invokes the ComputeWorker class to execute tasks
"""

from __future__ import annotations

import asyncio
import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from loguru import logger


class Args(Namespace):
    worker_id: str
    tasks: str | None
    log_level: str
    server_port: int
    worker_poll_interval: float

    def __init__(
        self,
        worker_id: str = "worker-default",
        tasks: str | None = None,
        log_level: str = "INFO",
        server_port: int = 8002,
    ) -> None:
        super().__init__()
        self.worker_id = worker_id
        self.tasks = tasks
        self.log_level = log_level
        self.server_port = server_port
        self.worker_poll_interval = 1.0


def main() -> int:
    """CLI entry point for worker."""
    parser = ArgumentParser(
        prog="compute-worker",
        description="Compute worker for task execution",
    )
    _ = parser.add_argument(
        "--worker-id",
        "-w",
        default="worker-default",
        help="Unique worker identifier (default: worker-default)",
    )
    _ = parser.add_argument(
        "--tasks",
        "-t",
        default=None,
        help="Comma-separated list of task types to process (default: all available)",
    )
    _ = parser.add_argument(
        "--log-level",
        "-l",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    _ = parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8002,
        help="Compute server port (default: 8002)",
        dest="server_port",
    )
    _ = parser.add_argument(
        "--worker-poll-interval",
        type=float,
        default=1.0,
        help="Polling interval for jobs in seconds (default: 1.0)",
    )

    args = parser.parse_args(namespace=Args())

    # Check that compute server is running on localhost
    # Worker requires server to be up (server creates directory and runs migrations)
    from .utils import ensure_server_running

    server_host = "localhost"
    print(f"Checking compute server at {server_host}:{args.server_port}...")
    try:
        ensure_server_running(server_host, args.server_port)
        print("✓ Server is running\n")
    except Exception as e:
        print(f"WARNING: Server check failed: {e}")
        print("Worker may fail if database/dirs are not ready.")

    # Check that CL_SERVER_DIR is valid (worker expects it to exist)
    # This handles the strict env check internally
    from .utils import ensure_cl_server_dir
    try:
        ensure_cl_server_dir(create_if_missing=False)
    except SystemExit:
        return 1
    
    # Initialize Config
    from .config import ComputeConfig
    config = ComputeConfig.from_cli_args(args)
    
    # Initialize Database (Worker needs access to DB)
    from . import database
    database.init_db(config)

    # Import ComputeWorker here after init
    from .worker import ComputeWorker

    # Parse tasks
    tasks = args.tasks.split(",") if args.tasks else None

    # Print startup info
    print(f"Starting compute worker: {args.worker_id}")
    print(f"Connected to server: {server_host}:{args.server_port}")
    print(f"Task filter: {tasks or 'all available'}")
    print(f"Log level: {args.log_level}")
    print(f"Database: {config.database_url}")
    print("Press Ctrl+C to stop\n")

    # Run worker
    try:
        asyncio.run(ComputeWorker.run_worker(args.worker_id, config, tasks))
        return 0
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
