import asyncio
import sys

from loguru import logger

from . import database
from .config import ComputeWorkerConfig
from .utils import ensure_server_running
from .worker import ComputeWorker

try:
    from cl_ml_tools.utils.mqtt.mqtt_impl import MQTTBroadcaster
except ImportError:
    MQTTBroadcaster = None


def main() -> int:
    """CLI entry point for worker."""
    # Initialize Config
    config = ComputeWorkerConfig.from_args()
    
    # Worker REQUIRES MQTT for capability broadcasting - validate early
    if not config.mqtt_url:
        print("ERROR: --mqtt-url is required for compute worker", file=sys.stderr)
        return 1

    # Validate MQTT URL format early
    if MQTTBroadcaster:
        try:
            MQTTBroadcaster.validate_mqtt_url(config.mqtt_url)
        except ValueError as e:
            print(f"ERROR: Invalid MQTT URL: {e}", file=sys.stderr)
            return 1

    # Check that compute server is running on localhost
    # Worker requires server to be up (server creates directory and runs migrations)
    server_host = "localhost"
    print(f"Checking compute server at {server_host}:{config.port}...")
    try:
        ensure_server_running(server_host, config.port)
        print("✓ Server is running\n")
    except Exception as e:
        print(f"WARNING: Server check failed: {e}")
        print("Worker may fail if database/dirs are not ready.")

    # Initialize Database (Worker needs access to DB)
    database.init_db(config)

    # Print startup info
    print(f"Starting compute worker: {config.worker_id}")
    print(f"Connected to server: {server_host}:{config.port}")
    print(f"MQTT URL: {config.mqtt_url}")
    print(f"Task filter: {config.worker_supported_tasks or 'all available'}")
    print(f"Log level: {config.log_level}")
    print(f"Database: {config.database_url}")
    print("Press Ctrl+C to stop\n")

    # Run worker
    try:
        asyncio.run(ComputeWorker.run_worker(config.worker_id, config, config.worker_supported_tasks))
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
