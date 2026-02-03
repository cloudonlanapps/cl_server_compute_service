"""Job status broadcaster for Compute service.

Handles broadcasting of job status updates to MQTT.
Ensures strict requirement for MQTT broadcaster availability.
"""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from cl_ml_tools import (
    JobStatus,
    MQTTBroadcaster,
)
from loguru import logger

if TYPE_CHECKING:
    from .config import ComputeConfigBase


class JobStatusBroadcaster:
    """Manages MQTT broadcasting of job status updates."""

    def __init__(self, config: ComputeConfigBase, broadcaster: MQTTBroadcaster | None = None):
        """Initialize broadcaster.
        
        Args:
            config: Compute service configuration
            broadcaster: Initialized MQTT broadcaster (optional)
        """
        self.config = config
        self.broadcaster: MQTTBroadcaster | None = broadcaster

    def set_broadcaster(self, broadcaster: MQTTBroadcaster) -> None:
        """Set or update the MQTT broadcaster.

        Args:
            broadcaster: Initialized MQTT broadcaster
        """
        self.broadcaster = broadcaster

    def broadcast_progress(self, job_id: str, status: JobStatus, progress: int) -> None:
        """Broadcast job progress update via MQTT.

        Args:
            job_id: Unique job identifier
            status: Current job status
            progress: Progress percentage (0-100)
        """
        payload = {
            "job_id": job_id,
            "event_type": status.value,
            "timestamp": int(time.time() * 1000),
            "progress": progress,
        }

        if not self.broadcaster:
            logger.warning(f"MQTT broadcaster not initialized, skipping job event: {job_id} {status.value}")
            return

        topic = self.config.mqtt_job_events_topic
        try:
            payload_str = json.dumps(payload)
            success = self.broadcaster.publish_event(topic=topic, payload=payload_str)
            if not success:
               logger.error(f"Failed to broadcast job event: topic={topic}, job_id={job_id}, status={status.value}")
        except Exception as e:
             logger.error(f"Exception during broadcast: {e}")
