"""Tests for worker capability manager."""

import json
from unittest.mock import MagicMock, patch

import pytest
from cl_ml_tools import MQTTBroadcaster
from compute.capability_manager import (
    CapabilityManager,
    CapabilityMessage,
    close_capability_manager,
    get_capability_manager,
    initialize_capability_manager,
)
from compute.config import ComputeConfig


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = MagicMock(spec=ComputeConfig)
    config.broadcast_type = "redis"
    config.mqtt_url = "mqtt://mock-broker:1883"
    config.capability_topic_prefix = "inference/workers"
    return config


class TestCapabilityMessage:
    """Tests for CapabilityMessage model."""

    def test_capability_message_valid(self):
        """Test CapabilityMessage with valid data."""
        msg = CapabilityMessage(
            id="worker-1",
            capabilities=["image_resize", "image_conversion"],
            idle_count=1,
            timestamp=1234567890000,
        )

        assert msg.id == "worker-1"
        assert msg.capabilities == ["image_resize", "image_conversion"]
        assert msg.idle_count == 1
        assert msg.timestamp == 1234567890000

    def test_capability_message_from_json(self):
        """Test parsing CapabilityMessage from JSON."""
        json_data = json.dumps(
            {
                "id": "worker-2",
                "capabilities": ["face_detection"],
                "idle_count": 0,
                "timestamp": 1234567890000,
            }
        )

        msg = CapabilityMessage.model_validate_json(json_data)

        assert msg.id == "worker-2"
        assert msg.capabilities == ["face_detection"]
        assert msg.idle_count == 0


class TestCapabilityManager:
    """Tests for CapabilityManager."""

    def test_capability_manager_init(self, mock_config):
        """Test CapabilityManager initialization."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)

        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        assert manager.capabilities_cache == {}
        assert manager.broadcaster == mock_broadcaster
        assert manager.ready_event.is_set()
        assert manager.config == mock_config
        mock_broadcaster.subscribe.assert_called_once()



    def test_on_message_valid_capability(self, mock_config):
        """Test processing valid capability message."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)

        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        # Simulate capability message
        topic = "inference/workers/worker-1"
        payload = json.dumps(
            {
                "id": "worker-1",
                "capabilities": ["image_resize", "image_conversion"],
                "idle_count": 1,
                "timestamp": 1234567890000,
            }
        )

        manager.on_message(topic, payload)

        assert "worker-1" in manager.capabilities_cache
        assert manager.capabilities_cache["worker-1"].id == "worker-1"
        assert "image_resize" in manager.capabilities_cache["worker-1"].capabilities

    def test_on_message_empty_payload(self, mock_config):
        """Test processing LWT empty message (worker disconnected)."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)

        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        # Add worker to cache first
        topic = "inference/workers/worker-1"
        payload = json.dumps(
            {
                "id": "worker-1",
                "capabilities": ["image_resize"],
                "idle_count": 1,
                "timestamp": 1234567890000,
            }
        )
        manager.on_message(topic, payload)
        assert "worker-1" in manager.capabilities_cache

        # Now send empty payload (LWT)
        manager.on_message(topic, "")

        # Worker should be removed from cache
        assert "worker-1" not in manager.capabilities_cache

    def test_on_message_invalid_topic(self, mock_config):
        """Test processing message with invalid topic format."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)

        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        # Topic with less than 3 parts
        manager.on_message("invalid/topic", '{"id": "test"}')

        # Should not crash, cache should remain empty
        assert len(manager.capabilities_cache) == 0

    def test_on_message_invalid_json(self, mock_config):
        """Test processing message with invalid JSON."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)
        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        topic = "inference/workers/worker-1"
        manager.on_message(topic, "invalid json{")

        # Should not crash, cache should remain empty
        assert len(manager.capabilities_cache) == 0

    def test_get_cached_capabilities_empty(self, mock_config):
        """Test getting capabilities when cache is empty."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)
        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        result = manager.get_cached_capabilities()

        assert result.root == {}

    def test_get_cached_capabilities_single_worker(self, mock_config):
        """Test getting capabilities with single worker."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)
        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        # Add worker capability
        topic = "inference/workers/worker-1"
        payload = json.dumps(
            {
                "id": "worker-1",
                "capabilities": ["image_resize", "image_conversion"],
                "idle_count": 1,
                "timestamp": 1234567890000,
            }
        )
        manager.on_message(topic, payload)

        result = manager.get_cached_capabilities()

        assert result.root["image_resize"] == 1
        assert result.root["image_conversion"] == 1

    def test_get_cached_capabilities_multiple_workers(self, mock_config):
        """Test aggregating capabilities from multiple workers."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)
        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        # Add first worker
        manager.on_message(
            "inference/workers/worker-1",
            json.dumps(
                {
                    "id": "worker-1",
                    "capabilities": ["image_resize", "image_conversion"],
                    "idle_count": 1,
                    "timestamp": 1234567890000,
                }
            ),
        )

        # Add second worker
        manager.on_message(
            "inference/workers/worker-2",
            json.dumps(
                {
                    "id": "worker-2",
                    "capabilities": ["image_resize", "face_detection"],
                    "idle_count": 2,
                    "timestamp": 1234567890000,
                }
            ),
        )

        result = manager.get_cached_capabilities()

        # image_resize: 1 + 2 = 3
        # image_conversion: 1
        # face_detection: 2
        assert result.root["image_resize"] == 3
        assert result.root["image_conversion"] == 1
        assert result.root["face_detection"] == 2

    def test_wait_for_capabilities(self, mock_config):
        """Test waiting for capability manager to be ready."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)
        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        # Should be immediately ready
        result = manager.wait_for_capabilities(timeout=1)

        assert result is True

    def test_get_worker_count_by_capability(self, mock_config):
        """Test getting worker count by capability."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)
        manager = CapabilityManager(mock_config, broadcaster=mock_broadcaster)

        # Add workers
        manager.on_message(
            "inference/workers/worker-1",
            json.dumps(
                {
                    "id": "worker-1",
                    "capabilities": ["image_resize", "image_conversion"],
                    "idle_count": 1,
                    "timestamp": 1234567890000,
                }
            ),
        )

        manager.on_message(
            "inference/workers/worker-2",
            json.dumps(
                {
                    "id": "worker-2",
                    "capabilities": ["image_resize"],
                    "idle_count": 0,
                    "timestamp": 1234567890000,
                }
            ),
        )

        result = manager.get_worker_count_by_capability()

        # Both workers have image_resize
        # Only worker-1 has image_conversion
        assert result.root["image_resize"] == 2
        assert result.root["image_conversion"] == 1



class TestCapabilityManagerSingleton:
    """Tests for capability manager singleton functions."""

    def test_get_capability_manager_singleton(self, mock_config):
        """Test that get_capability_manager returns singleton."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)
        
        # Reset singleton
        import compute.capability_manager

        compute.capability_manager._capability_manager_instance = None  # pyright: ignore[reportPrivateUsage]

        manager1 = initialize_capability_manager(mock_config, broadcaster=mock_broadcaster)
        manager2 = get_capability_manager()

        assert manager1 is manager2

        # Clean up
        compute.capability_manager._capability_manager_instance = None  # pyright: ignore[reportPrivateUsage]

    def test_close_capability_manager(self, mock_config):
        """Test closing capability manager singleton."""
        mock_broadcaster: MagicMock = MagicMock(spec=MQTTBroadcaster)

        # Reset singleton
        import compute.capability_manager

        compute.capability_manager._capability_manager_instance = None  # pyright: ignore[reportPrivateUsage]

        manager = initialize_capability_manager(mock_config, broadcaster=mock_broadcaster)
        assert manager is not None

        close_capability_manager()

        # Singleton should be None after closing
        assert compute.capability_manager._capability_manager_instance is None  # pyright: ignore[reportPrivateUsage]  for testing purposes
        
        # Ensure disconnect NOT called (managed by app)
        mock_broadcaster.disconnect.assert_not_called()

    def test_close_capability_manager_when_none(self):
        """Test closing when manager is already None."""
        import compute.capability_manager

        compute.capability_manager._capability_manager_instance = None  # pyright: ignore[reportPrivateUsage]  for testing purposes

        # Should not crash
        close_capability_manager()

        assert compute.capability_manager._capability_manager_instance is None  # pyright: ignore[reportPrivateUsage]  for testing purposes
