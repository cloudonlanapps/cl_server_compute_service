"""Compute worker implementation for task execution.

This module contains the ComputeWorker class that:
- Auto-discovers compute plugins from pyproject.toml entry points
- Polls for jobs from the shared database
- Executes tasks in-process using cl_ml_tools.Worker
- Broadcasts worker capabilities via MQTT for service discovery
- Handles graceful shutdown
"""

from __future__ import annotations

import asyncio
import signal
from types import FrameType
from typing import TYPE_CHECKING

from cl_ml_tools import Worker, shutdown_broadcaster
from loguru import logger

from .capability_broadcaster import CapabilityBroadcaster
from . import database
from .repository import JobRepositoryService
from .storage import JobStorageService

if TYPE_CHECKING:
    from .config import ComputeConfig

# Global shutdown event and signal counter
shutdown_event = asyncio.Event()
shutdown_signal_count = 0


def reset_shutdown_state() -> None:
    """Reset shutdown state for testing.

    This function is used by tests to reset the global shutdown state
    between test runs.
    """
    global shutdown_signal_count
    shutdown_event.clear()
    shutdown_signal_count = 0


def signal_handler(signum: int, _frame: FrameType | None) -> None:
    """Handle shutdown signals (SIGINT, SIGTERM).

    First signal: Initiates graceful shutdown
    Second signal: Forces immediate exit
    """
    import sys

    global shutdown_signal_count
    shutdown_signal_count += 1

    if shutdown_signal_count == 1:
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        logger.info("Press Ctrl+C again to force immediate exit")
        shutdown_event.set()
    else:
        # Use print to ensure message appears before exit
        print(
            "\nWARNING: Force exit requested, terminating immediately!",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)


class ComputeWorker:
    """Compute worker that executes jobs using cl_ml_tools."""

    def __init__(
        self,
        worker_id: str,
        config: ComputeConfig,
        supported_tasks: list[str] | None = None,
    ):
        """Initialize compute worker.

        Args:
            worker_id: Unique identifier for this worker
            config: Worker configuration
            supported_tasks: List of task types to process (None = all available)
        """
        self.worker_id: str = worker_id
        self.config = config
        self.poll_interval: float = config.worker_poll_interval

        # Create repository and storage adapters
        # Note: SessionLocal is global from database module, initialized by init_db
        if not database.SessionLocal:
             raise RuntimeError("Database not initialized. Call database.init_db() first.")
             
        self.repository: JobRepositoryService = JobRepositoryService(database.SessionLocal, config)
        
        if not config.compute_storage_dir:
            raise ValueError("Compute storage directory not configured")
            
        self.job_storage: JobStorageService = JobStorageService(base_dir=config.compute_storage_dir)

        # Create cl_ml_tools Worker (auto-discovers plugins)
        logger.info("Initializing cl_ml_tools Worker...")
        self.library_worker: Worker = Worker(
            repository=self.repository,
            job_storage=self.job_storage,
        )

        # Determine active task types
        available_tasks = set(self.library_worker.get_supported_task_types())
        requested_tasks = (
            set(supported_tasks)
            if supported_tasks
            else (
                set(config.worker_supported_tasks)
                if config.worker_supported_tasks
                else available_tasks
            )
        )

        # Active tasks = intersection of requested and available
        self.active_tasks: set[str] = available_tasks & requested_tasks

        # Log initialization details
        logger.info(f"Worker {worker_id} initialized")
        logger.info(f"  Requested tasks: {sorted(requested_tasks)}")
        logger.info(f"  Available plugins: {sorted(available_tasks)}")
        logger.info(f"  Active tasks: {sorted(self.active_tasks)}")

        # Validate we have tasks to process
        if not self.active_tasks:
            if requested_tasks and not available_tasks:
                raise RuntimeError(
                    "No compute plugins found! Ensure cl_ml_tools is installed with "
                    + "task plugins registered in pyproject.toml"
                )
            elif requested_tasks and available_tasks:
                raise RuntimeError(
                    f"No matching plugins found. Requested: {sorted(requested_tasks)}, "
                    + f"Available: {sorted(available_tasks)}"
                )
            else:
                raise RuntimeError("No task types specified")

        # Initialize capability broadcaster
        self.capability_broadcaster: CapabilityBroadcaster = CapabilityBroadcaster(
            worker_id=worker_id, active_tasks=self.active_tasks, config=config
        )

    async def _heartbeat_task(self):
        """Background task to periodically publish worker capabilities."""
        logger.info(f"Heartbeat task started (interval: {self.config.mqtt_heartbeat_interval}s)")
        try:
            while not shutdown_event.is_set():
                await asyncio.sleep(self.config.mqtt_heartbeat_interval)
                if not shutdown_event.is_set():
                    self.capability_broadcaster.publish()
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Error in heartbeat task: {e}", exc_info=True)

    async def _process_next_job(self) -> bool:
        """Process one job using cl_ml_tools Worker.

        Returns:
            True if a job was processed, False if no jobs available
        """
        # Mark as busy and publish
        self.capability_broadcaster.is_idle = False
        self.capability_broadcaster.publish()

        try:
            # Use library worker to fetch and process one job
            task_types = list(self.active_tasks)
            processed = await self.library_worker.run_once(task_types=task_types)

            if processed:
                logger.info("Job processed successfully")
                return True
            else:
                logger.debug("No jobs available")
                return False

        except Exception as e:
            logger.exception(f"Error processing job: {e}")
            return False
        finally:
            # Mark as idle and publish
            self.capability_broadcaster.is_idle = True
            self.capability_broadcaster.publish()

    async def run(self):
        """Main worker loop - poll for jobs and execute them."""
        logger.info(f"Worker {self.worker_id} starting...")

        # Initialize capability broadcaster
        self.capability_broadcaster.init()

        # Publish initial capabilities
        self.capability_broadcaster.publish()

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_task())

        try:
            while not shutdown_event.is_set():
                try:
                    processed = await self._process_next_job()
                    if not processed:
                        # No job found, sleep before polling again
                        await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    logger.info("Worker cancelled")
                    break
                except Exception as e:
                    logger.exception(f"Error in worker loop: {e}")
                    await asyncio.sleep(self.poll_interval)
        finally:
            logger.info(f"Worker {self.worker_id} shutting down...")

            # Cancel heartbeat task first to prevent race conditions
            _ = heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            # Clear retained capability message
            self.capability_broadcaster.clear()

    @classmethod
    async def run_worker(cls, worker_id: str, config: ComputeConfig, tasks: list[str] | None):
        """Create and run worker with given configuration.

        Args:
            worker_id: Unique worker identifier
            config: Worker configuration
            tasks: List of task types to process (None = all available)
        """
        # Register signal handlers for graceful shutdown
        _ = signal.signal(signal.SIGINT, signal_handler)
        _ = signal.signal(signal.SIGTERM, signal_handler)

        worker = cls(
            worker_id=worker_id,
            config=config,
            supported_tasks=tasks,
        )

        try:
            await worker.run()
        finally:
            # Shutdown broadcaster
            shutdown_broadcaster()
