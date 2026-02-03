"""Compute worker CLI entry point.

This CLI:
- Parses command-line arguments
- Configures logging
- Invokes the ComputeWorker class to execute tasks
"""

from __future__ import annotations

import asyncio
import sys

from urllib.parse import urlparse
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


    # Parse compute_url to get host and port
    parsed_url = urlparse(config.compute_url)
    server_host = parsed_url.hostname
    server_port = parsed_url.port
    
    if not server_host or not server_port:
        raise ValueError(f"Invalid compute_url: {config.compute_url}. Must include scheme, hostname, and port (e.g., http://localhost:8002)")
    
    print(f"Checking compute server at {server_host}:{server_port}...")
    ensure_server_running(server_host, server_port)
    print("✓ Server is running\n")

    # Initialize Database (Worker needs access to DB)
    from . import database
    database.init_db(config)

    # Import ComputeWorker here after init
    from .worker import ComputeWorker

    # Print startup info
    print(f"Starting compute worker: {config.worker_id}")
    print(f"Connected to server: {server_host}:{server_port}")
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
