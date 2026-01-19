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
    database_url: str
    cl_server_dir: str

    def __init__(
        self,
        worker_id: str = "worker-default",
        tasks: str | None = None,
        log_level: str = "INFO",
        server_port: int = 8002,
        database_url: str = "",
        cl_server_dir: str = "",
    ) -> None:
        super().__init__()
        self.worker_id = worker_id
        self.tasks = tasks
        self.log_level = log_level
        self.server_port = server_port
        self.database_url = database_url
        self.cl_server_dir = cl_server_dir


def main() -> int:
    """CLI entry point for worker."""
    # Get defaults from env before importing Config
    default_worker_id = os.getenv("WORKER_ID", "worker-default")
    default_log_level = os.getenv("LOG_LEVEL", "INFO")
    default_server_port = int(os.getenv("COMPUTE_SERVER_PORT", "8002"))

    parser = ArgumentParser(
        prog="compute-worker",
        description="Compute worker for task execution",
    )
    _ = parser.add_argument(
        "--worker-id",
        "-w",
        default=default_worker_id,
        help=f"Unique worker identifier (default: {default_worker_id})",
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
        default=default_log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Logging level (default: {default_log_level})",
    )
    _ = parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=default_server_port,
        help=f"Compute server port (default: {default_server_port})",
        dest="server_port",
    )
    _ = parser.add_argument(
        "--database-url",
        default=os.getenv("WORKER_DATABASE_URL", ""),
        help="Database URL (default: sqlite:///compute.db)",
    )
    _ = parser.add_argument(
        "--cl-server-dir", 
        default=os.getenv("CL_SERVER_DIR", ""),
        help="Root directory for CoLAN Server data"
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

    # Ensure CL_SERVER_DIR exists if provided
    if args.cl_server_dir:
        cl_dir = Path(args.cl_server_dir)
        if not cl_dir.exists():
            print(f"WARNING: --cl-server-dir {cl_dir} does not exist.")
        else:
             os.environ["CL_SERVER_DIR"] = str(cl_dir)
    
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
