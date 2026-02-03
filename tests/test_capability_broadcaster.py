"""Tests for capability broadcaster."""

import json
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from cl_ml_tools import MQTTBroadcaster
from compute.capability_broadcaster import CapabilityBroadcaster


class TestCapabilityBroadcaster:
    """Tests for CapabilityBroadcaster."""

    def test_capability_broadcaster_init(self):
        """Test CapabilityBroadcaster initialization."""
        mock_compute_config = MagicMock()
        mock_compute_config.capability_topic_prefix = "capabilities"
        mock_compute_config.broadcast_type = "redis"
        
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize", "image_conversion"},
            config=mock_compute_config,
            broadcaster=mock_broadcaster
        )

        assert broadcaster.worker_id == "worker-1"
        assert broadcaster.active_tasks == {"image_resize", "image_conversion"}
        assert broadcaster.is_idle is True
        assert broadcaster.broadcaster == mock_broadcaster
        assert "worker-1" in broadcaster.topic
        mock_broadcaster.set_will.assert_called_once()

    def test_publish_success(self):
        """Test publishing capabilities successfully."""
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)
        mock_broadcaster.publish_retained.return_value = True

        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.broadcast_type = "redis"
        mock_config.mqtt_url = "mqtt://mock-broker:1883"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize", "image_conversion"},
            config=mock_config,
            broadcaster=mock_broadcaster
        )

        broadcaster.publish()

        # Verify publish_retained was called
        mock_broadcaster.publish_retained.assert_called_once()
        call_args = mock_broadcaster.publish_retained.call_args

        # Verify topic
        assert "worker-1" in call_args[1]["topic"]

        # Verify payload structure
        payload = call_args[1]["payload"]
        assert isinstance(payload, str)
        data: dict[str, object] = cast(dict[str, object], json.loads(payload))
        assert data["worker_id"] == "worker-1"
        assert set(cast(list[str], data["capabilities"])) == {
            "image_resize",
            "image_conversion",
        }
        assert data["idle_count"] == 1  # is_idle is True by default
        assert "timestamp" in data

    def test_publish_when_busy(self):
        """Test publishing when worker is busy."""
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)
        mock_broadcaster.publish_retained.return_value = True

        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.broadcast_type = "redis"
        mock_config.mqtt_url = "mqtt://mock-broker:1883"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config,
            broadcaster=mock_broadcaster
        )
        broadcaster.is_idle = False

        broadcaster.publish()

        # Verify payload has idle_count=0
        call_args = mock_broadcaster.publish_retained.call_args
        payload = call_args[1]["payload"]
        assert isinstance(payload, str)
        data: dict[str, object] = cast(dict[str, object], json.loads(payload))
        assert data["idle_count"] == 0

    def test_publish_failure(self):
        """Test publishing when publish fails."""
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)
        mock_broadcaster.publish_retained.return_value = False

        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.broadcast_type = "redis"
        mock_config.mqtt_url = "mqtt://mock-broker:1883"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config,
            broadcaster=mock_broadcaster
        )

        # Should not crash
        broadcaster.publish()

        mock_broadcaster.publish_retained.assert_called_once()

    def test_publish_without_init(self):
        """Test publishing without initializing broadcaster."""
        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config,
            broadcaster=cast(MQTTBroadcaster, None)
        )

        # broadcaster is None, should not crash
        broadcaster.publish()

        # No exception should be raised

    def test_clear_success(self):
        """Test clearing retained capabilities."""
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)
        mock_broadcaster.clear_retained.return_value = True

        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.broadcast_type = "redis"
        mock_config.mqtt_url = "mqtt://mock-broker:1883"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config,
            broadcaster=mock_broadcaster
        )

        broadcaster.clear()

        mock_broadcaster.clear_retained.assert_called_once()
        call_args = mock_broadcaster.clear_retained.call_args
        assert "worker-1" in call_args[0][0]

    def test_clear_failure(self):
        """Test clearing when clear fails."""
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)
        mock_broadcaster.clear_retained.return_value = False

        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.broadcast_type = "redis"
        mock_config.mqtt_url = "mqtt://mock-broker:1883"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config,
            broadcaster=mock_broadcaster
        )

        # Should not crash
        broadcaster.clear()

        mock_broadcaster.clear_retained.assert_called_once()

    def test_clear_without_init(self):
        """Test clearing without initializing broadcaster."""
        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config,
            broadcaster=cast(MQTTBroadcaster, None)
        )

        # broadcaster is None, should not crash
        broadcaster.clear()

        # No exception should be raised

    def test_topic_format(self):
        """Test that topic uses correct format."""
        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "test/workers"
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-123",
            active_tasks=set(),
            config=mock_config,
            broadcaster=mock_broadcaster
        )

        assert broadcaster.topic == "test/workers/worker-123"

    def test_publish_with_empty_tasks(self):
        """Test publishing with no active tasks."""
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)
        mock_broadcaster.publish_retained.return_value = True

        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.broadcast_type = "redis"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks=set(),  # Empty set
            config=mock_config,
            broadcaster=mock_broadcaster
        )

        broadcaster.publish()

        call_args = mock_broadcaster.publish_retained.call_args
        payload = call_args[1]["payload"]
        assert isinstance(payload, str)
        data: dict[str, object] = cast(dict[str, object], json.loads(payload))
        assert data["capabilities"] == []

    def test_idle_state_toggle(self):
        """Test toggling idle state."""
        mock_broadcaster = MagicMock(spec=MQTTBroadcaster)
        mock_broadcaster.publish_retained.return_value = True

        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.broadcast_type = "redis"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"task1"},
            config=mock_config,
            broadcaster=mock_broadcaster
        )

        assert broadcaster.is_idle is True
        broadcaster.publish()
        payload1 = str(mock_broadcaster.publish_retained.call_args[1]["payload"])
        data1: dict[str, object] = cast(dict[str, object], json.loads(payload1))
        assert data1["idle_count"] == 1

        # Set to busy
        broadcaster.is_idle = False
        broadcaster.publish()
        payload2 = str(mock_broadcaster.publish_retained.call_args[1]["payload"])
        data2: dict[str, object] = cast(dict[str, object], json.loads(payload2))
        assert data2["idle_count"] == 0

        # Set back to idle
        broadcaster.is_idle = True
        broadcaster.publish()
        payload3 = str(mock_broadcaster.publish_retained.call_args[1]["payload"])
        data3: dict[str, object] = cast(dict[str, object], json.loads(payload3))
        assert data3["idle_count"] == 1
