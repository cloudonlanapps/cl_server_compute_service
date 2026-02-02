"""Tests for capability broadcaster."""

import json
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from compute.capability_broadcaster import CapabilityBroadcaster


class TestCapabilityBroadcaster:
    """Tests for CapabilityBroadcaster."""


    def test_capability_broadcaster_init(self, mqtt_url: str):
        """Test CapabilityBroadcaster initialization."""
        mock_compute_config = MagicMock()
        mock_compute_config.capability_topic_prefix = "capabilities"
        mock_compute_config.mqtt_url = mqtt_url
        
        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize", "image_conversion"},
            config=mock_compute_config,
        )

        assert broadcaster.worker_id == "worker-1"
        assert broadcaster.active_tasks == {"image_resize", "image_conversion"}
        assert broadcaster.is_idle is True
        assert broadcaster.broadcaster is None
        assert "worker-1" in broadcaster.topic

    def test_init_mqtt_broadcaster(self, mqtt_url: str):
        """Test initializing MQTT broadcaster."""
        with patch("compute.capability_broadcaster.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster
            
            mock_config = MagicMock()
            mock_config.capability_topic_prefix = "capabilities"
            mock_config.mqtt_url = mqtt_url

            broadcaster = CapabilityBroadcaster(
                worker_id="worker-1",
                active_tasks={"image_resize"},
                config=mock_config,
            )

            broadcaster.init()

            assert broadcaster.broadcaster is not None
            mock_get_broadcaster.assert_called_once_with(mqtt_url=mqtt_url)
            mock_broadcaster.set_will.assert_called_once()  # pyright: ignore[reportAny] ignore mock types for testing purposes

    def test_init_mqtt_broadcaster_raises_when_mqtt_disabled(self):
        """Test init raises when mqtt_url is None (workers require MQTT)."""
        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.mqtt_url = None

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config
        )

        with pytest.raises(ValueError, match="mqtt_url"):
            broadcaster.init()

    def test_publish_success(self, mqtt_url: str):
        """Test publishing capabilities successfully."""
        with patch("compute.capability_broadcaster.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_broadcaster.publish_retained.return_value = True  # pyright: ignore[reportAny] ignore mock types for testing purposes
            mock_get_broadcaster.return_value = mock_broadcaster

            mock_config = MagicMock()
            mock_config.capability_topic_prefix = "capabilities"
            mock_config.mqtt_url = mqtt_url

            broadcaster = CapabilityBroadcaster(
                worker_id="worker-1",
                active_tasks={"image_resize", "image_conversion"},
                config=mock_config
            )
            broadcaster.init()

            broadcaster.publish()

            # Verify publish_retained was called
            mock_broadcaster.publish_retained.assert_called_once()  # pyright: ignore[reportAny] ignore mock types for testing purposes
            call_args = mock_broadcaster.publish_retained.call_args  # pyright: ignore[reportAny] ignore mock types for testing purposes

            # Verify topic
            assert "worker-1" in call_args[1]["topic"]

            # Verify payload structure
            payload = call_args[1]["payload"]  # pyright: ignore[reportAny] ignore mock types for testing purposes
            assert isinstance(payload, str)
            data: dict[str, object] = cast(dict[str, object], json.loads(payload))
            assert data["worker_id"] == "worker-1"
            assert set(cast(list[str], data["capabilities"])) == {
                "image_resize",
                "image_conversion",
            }
            assert data["idle_count"] == 1  # is_idle is True by default
            assert "timestamp" in data

    def test_publish_when_busy(self, mqtt_url: str):
        """Test publishing when worker is busy."""
        with patch("compute.capability_broadcaster.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster = MagicMock()
            mock_broadcaster.publish_retained.return_value = True  # pyright: ignore[reportAny] ignore mock types for testing purposes
            mock_get_broadcaster.return_value = mock_broadcaster

            mock_config = MagicMock()
            mock_config.capability_topic_prefix = "capabilities"
            mock_config.mqtt_url = mqtt_url

            broadcaster = CapabilityBroadcaster(
                worker_id="worker-1",
                active_tasks={"image_resize"},
                config=mock_config
            )
            broadcaster.init()
            broadcaster.is_idle = False

            broadcaster.publish()

            # Verify payload has idle_count=0
            call_args = mock_broadcaster.publish_retained.call_args  # pyright: ignore[reportAny] ignore mock types for testing purposes
            payload = call_args[1]["payload"]  # pyright: ignore[reportAny] ignore mock types for testing purposes
            assert isinstance(payload, str)
            data: dict[str, object] = cast(dict[str, object], json.loads(payload))
            assert data["idle_count"] == 0

    def test_publish_failure(self, mqtt_url: str):
        """Test publishing when publish fails."""
        with patch("compute.capability_broadcaster.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster = MagicMock()
            mock_broadcaster.publish_retained.return_value = False  # pyright: ignore[reportAny] ignore mock types for testing purposes
            mock_get_broadcaster.return_value = mock_broadcaster

            mock_config = MagicMock()
            mock_config.capability_topic_prefix = "capabilities"
            mock_config.mqtt_url = mqtt_url

            broadcaster = CapabilityBroadcaster(
                worker_id="worker-1",
                active_tasks={"image_resize"},
                config=mock_config
            )
            broadcaster.init()

            # Should not crash
            broadcaster.publish()

            mock_broadcaster.publish_retained.assert_called_once()  # pyright: ignore[reportAny] ignore mock types for testing purposes

    def test_publish_without_init(self):
        """Test publishing without initializing broadcaster."""
        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config
        )

        # broadcaster is None, should not crash
        broadcaster.publish()

        # No exception should be raised

    def test_clear_success(self, mqtt_url: str):
        """Test clearing retained capabilities."""
        with patch("compute.capability_broadcaster.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster = MagicMock()
            mock_broadcaster.clear_retained.return_value = True  # pyright: ignore[reportAny] ignore mock types for testing purposes
            mock_get_broadcaster.return_value = mock_broadcaster

            mock_config = MagicMock()
            mock_config.capability_topic_prefix = "capabilities"
            mock_config.mqtt_url = mqtt_url

            broadcaster = CapabilityBroadcaster(
                worker_id="worker-1",
                active_tasks={"image_resize"},
                config=mock_config
            )
            broadcaster.init()

            broadcaster.clear()

            mock_broadcaster.clear_retained.assert_called_once()  # pyright: ignore[reportAny] ignore mock types for testing purposes
            call_args = mock_broadcaster.clear_retained.call_args  # pyright: ignore[reportAny] ignore mock types for testing purposes
            assert "worker-1" in call_args[0][0]

    def test_clear_failure(self, mqtt_url: str):
        """Test clearing when clear fails."""
        with patch("compute.capability_broadcaster.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster = MagicMock()
            mock_broadcaster.clear_retained.return_value = False  # pyright: ignore[reportAny] ignore mock types for testing purposes
            mock_get_broadcaster.return_value = mock_broadcaster

            mock_config = MagicMock()
            mock_config.capability_topic_prefix = "capabilities"
            mock_config.mqtt_url = mqtt_url

            broadcaster = CapabilityBroadcaster(
                worker_id="worker-1",
                active_tasks={"image_resize"},
                config=mock_config
            )
            broadcaster.init()

            # Should not crash
            broadcaster.clear()

            mock_broadcaster.clear_retained.assert_called_once()  # pyright: ignore[reportAny] ignore mock types for testing purposes

    def test_clear_without_init(self):
        """Test clearing without initializing broadcaster."""
        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "capabilities"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-1",
            active_tasks={"image_resize"},
            config=mock_config
        )

        # broadcaster is None, should not crash
        broadcaster.clear()

        # No exception should be raised

    def test_topic_format(self):
        """Test that topic uses correct format."""
        mock_config = MagicMock()
        mock_config.capability_topic_prefix = "test/workers"

        broadcaster = CapabilityBroadcaster(
            worker_id="worker-123",
            active_tasks=set(),
            config=mock_config
        )

        assert broadcaster.topic == "test/workers/worker-123"

    def test_publish_with_empty_tasks(self, mqtt_url: str):
        """Test publishing with no active tasks."""
        with patch("compute.capability_broadcaster.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_broadcaster.publish_retained.return_value = True  # pyright: ignore[reportAny] ignore mock types for testing purposes
            mock_get_broadcaster.return_value = mock_broadcaster

            mock_config = MagicMock()
            mock_config.capability_topic_prefix = "capabilities"
            mock_config.mqtt_url = mqtt_url

            broadcaster = CapabilityBroadcaster(
                worker_id="worker-1",
                active_tasks=set(),  # Empty set
                config=mock_config
            )
            broadcaster.init()

            broadcaster.publish()

            call_args = mock_broadcaster.publish_retained.call_args  # pyright: ignore[reportAny] ignore mock types for testing purposes
            payload = call_args[1]["payload"]  # pyright: ignore[reportAny] ignore mock types for testing purposes
            assert isinstance(payload, str)
            data: dict[str, object] = cast(dict[str, object], json.loads(payload))
            assert data["capabilities"] == []

    def test_idle_state_toggle(self, mqtt_url: str):
        """Test toggling idle state."""
        with patch("compute.capability_broadcaster.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster = MagicMock()
            mock_broadcaster.publish_retained.return_value = True  # pyright: ignore[reportAny] ignore mock types for testing purposes
            mock_get_broadcaster.return_value = mock_broadcaster

            mock_config = MagicMock()
            mock_config.capability_topic_prefix = "capabilities"
            mock_config.mqtt_url = mqtt_url

            broadcaster = CapabilityBroadcaster(
                worker_id="worker-1",
                active_tasks={"task1"},
                config=mock_config
            )
            broadcaster.init()

            assert broadcaster.is_idle is True
            broadcaster.publish()
            payload1 = str(mock_broadcaster.publish_retained.call_args[1]["payload"])  # pyright: ignore[reportAny] ignore mock types for testing purposes
            data1: dict[str, object] = cast(dict[str, object], json.loads(payload1))
            assert data1["idle_count"] == 1

            # Set to busy
            broadcaster.is_idle = False
            broadcaster.publish()
            payload2 = str(mock_broadcaster.publish_retained.call_args[1]["payload"])  # pyright: ignore[reportAny] ignore mock types for testing purposes
            data2: dict[str, object] = cast(dict[str, object], json.loads(payload2))
            assert data2["idle_count"] == 0

            # Set back to idle
            broadcaster.is_idle = True
            broadcaster.publish()
            payload3 = str(mock_broadcaster.publish_retained.call_args[1]["payload"])  # pyright: ignore[reportAny] ignore mock types for testing purposes
            data3: dict[str, object] = cast(dict[str, object], json.loads(payload3))
            assert data3["idle_count"] == 1
