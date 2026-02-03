from __future__ import annotations

import time
from typing import TYPE_CHECKING
from cl_ml_tools import MQTTBroadcaster
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .config import ComputeWorkerConfig

class WorkerCapability(BaseModel):
    """Individual worker capability information (from MQTT messages)."""

    model_config: ConfigDict = ConfigDict(populate_by_name=True)  # pyright: ignore[reportIncompatibleVariableOverride]

    worker_id: str = Field(..., description="Worker unique ID")
    capabilities: list[str] = Field(..., description="List of task types worker supports")
    idle_count: int = Field(..., description="1 if idle, 0 if busy")
    timestamp: int = Field(..., description="Message timestamp (milliseconds)")


class CapabilityBroadcaster:
    """Manages MQTT broadcasting of worker capabilities for service discovery."""

    def __init__(self, worker_id: str, active_tasks: set[str], config: ComputeWorkerConfig, broadcaster: MQTTBroadcaster):
        """Initialize capability broadcaster.

        Args:
            worker_id: Unique identifier for this worker
            active_tasks: Set of task types this worker can execute
            config: Compute service configuration
            broadcaster: Initialized MQTT broadcaster
        """
        self.worker_id: str = worker_id
        self.active_tasks: set[str] = active_tasks
        self.config = config
        self.is_idle: bool = True
        self.broadcaster: MQTTBroadcaster = broadcaster
        self.topic: str = f"{config.capability_topic_prefix}/{worker_id}"

        # Set Last Will & Testament (LWT) - published when worker disconnects
        if self.broadcaster:
            _ = self.broadcaster.set_will(topic=self.topic, payload="", qos=1, retain=True)
        logger.info(f"MQTT broadcaster initialized for worker {self.worker_id}")

    def publish(self):
        """Publish current worker capabilities to MQTT."""
        if not self.broadcaster:
            logger.warning("MQTT broadcaster not initialized, skipping capability publish")
            return

        capabilities_msg = WorkerCapability(
            worker_id=self.worker_id,
            capabilities=list(self.active_tasks),
            idle_count=1 if self.is_idle else 0,
            timestamp=int(time.time() * 1000),
        )

        payload = capabilities_msg.model_dump_json()
        success = self.broadcaster.publish_retained(topic=self.topic, payload=payload, qos=1)

        if success:
            logger.debug(f"Published capabilities: {list(self.active_tasks)}, idle: {self.is_idle}")
        else:
            logger.error(f"Failed to publish capabilities to {self.topic}")

    def clear(self):
        """Clear retained worker capabilities from MQTT (on shutdown)."""
        if not self.broadcaster:
            return

        success = self.broadcaster.clear_retained(self.topic)
        if success:
            logger.info(f"Cleared retained capabilities from {self.topic}")
        else:
            logger.error(f"Failed to clear retained capabilities from {self.topic}")
