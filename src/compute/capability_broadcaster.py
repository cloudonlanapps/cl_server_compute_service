import json
import time

from cl_ml_tools import (
    BroadcasterBase,
    get_broadcaster,
)
from cl_server_shared import Config
from loguru import logger


class CapabilityBroadcaster:
    """Manages MQTT broadcasting of worker capabilities for service discovery."""

    def __init__(self, worker_id: str, active_tasks: set[str]):
        """Initialize capability broadcaster.

        Args:
            worker_id: Unique identifier for this worker
            active_tasks: Set of task types this worker can execute
        """
        self.worker_id: str = worker_id
        self.active_tasks: set[str] = active_tasks
        self.is_idle: bool = True
        self.broadcaster: BroadcasterBase | None = (
            None  # Type from cl_ml_tools (not exported)
        )
        self.topic: str = f"{Config.CAPABILITY_TOPIC_PREFIX}/{worker_id}"

    def init(self):
        """Initialize MQTT broadcaster and set Last Will & Testament."""
        self.broadcaster = get_broadcaster(
            broadcast_type=Config.BROADCAST_TYPE,
            broker=Config.MQTT_BROKER,
            port=Config.MQTT_PORT,
        )

        # Set Last Will & Testament (LWT) - published when worker disconnects
        if self.broadcaster:
            _ = self.broadcaster.set_will(
                topic=self.topic, payload="", qos=1, retain=True
            )
            logger.info(f"MQTT broadcaster initialized for worker {self.worker_id}")

    def publish(self):
        """Publish current worker capabilities to MQTT."""
        if not self.broadcaster:
            logger.warning(
                "MQTT broadcaster not initialized, skipping capability publish"
            )
            return

        capabilities_msg = {
            "id": self.worker_id,
            "capabilities": list(self.active_tasks),
            "idle_count": 1 if self.is_idle else 0,
            "timestamp": int(time.time() * 1000),
        }

        payload = json.dumps(capabilities_msg)
        success = self.broadcaster.publish_retained(
            topic=self.topic, payload=payload, qos=1
        )

        if success:
            logger.debug(
                f"Published capabilities: {list(self.active_tasks)}, idle: {self.is_idle}"
            )
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
