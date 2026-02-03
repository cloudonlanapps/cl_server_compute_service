"""Compute worker CLI entry point.

This CLI:
- Parses command-line arguments
- Configures logging
- Invokes the ComputeWorker class to execute tasks
"""

from __future__ import annotations

import asyncio
import sys

from loguru import logger
from .config import ComputeWorkerConfig


def main() -> int:
    """CLI entry point for worker."""
    
    # Initialize Config via Singleton
    try:
        config = ComputeWorkerConfig.get_config()
    except SystemExit:
         # ArgumentParser raises SystemExit on --help or error
        return 1
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1

    # Check that compute server is running on localhost
    # Worker requires server to be up (server creates directory and runs migrations)
    from .utils import ensure_server_running

    server_host = "localhost"
    print(f"Checking compute server at {server_host}:{config.server_port}...")
    try:
        ensure_server_running(server_host, config.server_port)
        print("✓ Server is running\n")
    except Exception as e:
        print(f"WARNING: Server check failed: {e}")
        print("Worker may fail if database/dirs are not ready.")

    # Initialize Database (Worker needs access to DB)
    from . import database
    database.init_db(config)

    # Import ComputeWorker here after init
    from .worker import ComputeWorker

    # Print startup info
    print(f"Starting compute worker: {config.worker_id}")
    print(f"Connected to server: {server_host}:{config.server_port}")
    print(f"Task filter: {config.worker_supported_tasks or 'all available'}")
    print(f"Log level: {config.log_level}")
    print(f"Database: {config.database_url}")
    print("Press Ctrl+C to stop\n")

    # Run worker
    try:
        asyncio.run(ComputeWorker.run_worker(config))
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
