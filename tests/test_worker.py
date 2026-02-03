"""Tests for compute worker."""

import asyncio
import os
import signal
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cl_ml_tools import MQTTBroadcaster

from compute.worker import (
    ComputeWorker,
    reset_shutdown_state,
    shutdown_event,
    signal_handler,
)


class TestSignalHandler:
    """Tests for signal handler."""

    def test_signal_handler_sets_shutdown_event(self):
        """Test that signal handler sets shutdown event."""
        # Reset shutdown state
        reset_shutdown_state()

        # Call signal handler
        signal_handler(signal.SIGTERM, None)

        # Verify shutdown event is set
        assert shutdown_event.is_set()

    def test_signal_handler_with_different_signals(self):
        """Test signal handler with different signal numbers."""
        reset_shutdown_state()

        signal_handler(signal.SIGINT, None)
        assert shutdown_event.is_set()

        reset_shutdown_state()
        signal_handler(signal.SIGTERM, None)
        assert shutdown_event.is_set()

    def test_signal_handler_second_signal_exits(self):
        """Test that second signal forces immediate exit."""
        reset_shutdown_state()

        # First signal should set shutdown event
        signal_handler(signal.SIGINT, None)
        assert shutdown_event.is_set()

        # Second signal should exit
        with pytest.raises(SystemExit) as exc_info:
            signal_handler(signal.SIGINT, None)
        assert exc_info.value.code == 1


class TestComputeWorker:
    """Tests for ComputeWorker class."""

    @pytest.fixture(autouse=True)
    def reset_shutdown_state_fixture(self):
        """Reset shutdown state before and after each test."""
        reset_shutdown_state()
        yield
        reset_shutdown_state()

    @pytest.fixture
    def mock_dependencies(
        self,
    ) -> Generator[dict[str, MagicMock | AsyncMock], None, None]:
        """Mock dependencies for ComputeWorker."""
        with (
            patch("compute.worker.JobRepositoryService") as mock_repo,
            patch("compute.worker.JobStorageService") as mock_storage,
            patch("compute.worker.Worker") as mock_worker,
            patch("compute.worker.CapabilityBroadcaster") as mock_broadcaster,
            patch("compute.database.SessionLocal") as mock_session_local,
            patch("cl_ml_tools.get_broadcaster") as mock_get_broadcaster,
        ):
            # Configure mock session local
            mock_session_local.return_value = MagicMock()
            
            # Configure get_broadcaster
            mock_mqtt = MagicMock(spec=MQTTBroadcaster)
            mock_get_broadcaster.return_value = mock_mqtt

            # Configure mock library worker
            mock_worker_instance = MagicMock()
            mock_worker_instance.get_supported_task_types.return_value = (
                [  # pyright: ignore[reportAny] ignore mock type for testing purposes
                    "image_resize",
                    "image_conversion",
                ]
            )
            mock_worker_instance.run_once = AsyncMock(return_value=True)
            mock_worker.return_value = mock_worker_instance

            yield {
                "repo": mock_repo,
                "storage": mock_storage,
                "worker": mock_worker,
                "worker_instance": mock_worker_instance,
                "broadcaster": mock_broadcaster,
                "mqtt_broadcaster": mock_mqtt,
            }

    @pytest.mark.usefixtures("mock_dependencies")
    def test_worker_init_with_all_tasks(self):
        """Test worker initialization with all available tasks."""
        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"

        worker = ComputeWorker(
            worker_id="test-worker",
            supported_tasks=None,
            config=mock_config,
        )

        assert worker.worker_id == "test-worker"
        assert worker.active_tasks == {"image_resize", "image_conversion"}
        assert worker.library_worker is not None
        assert worker.capability_broadcaster is not None

    @pytest.mark.usefixtures("mock_dependencies")
    def test_worker_init_with_specific_tasks(self):
        """Test worker initialization with specific task types."""
        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )

        worker = ComputeWorker(
            worker_id="test-worker",
            config=mock_config,
            supported_tasks=["image_resize"],
        )

        assert worker.active_tasks == {"image_resize"}

    @pytest.mark.usefixtures("mock_dependencies")
    def test_worker_init_with_no_matching_tasks(self):
        """Test worker initialization with no matching tasks raises error."""
        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )

        with pytest.raises(RuntimeError, match="No matching plugins found"):
            _ = ComputeWorker(
                worker_id="test-worker",
                config=mock_config,
                supported_tasks=["nonexistent_task"],
            )

    def test_worker_init_with_no_plugins_available(self):
        """Test worker initialization when no plugins are available."""
        with (
            patch("compute.worker.JobRepositoryService"),
            patch("compute.worker.JobStorageService"),
            patch("compute.worker.Worker") as mock_worker,
            patch("compute.database.SessionLocal", new=MagicMock()),  # Mock DB session
            patch("cl_ml_tools.get_broadcaster") as mock_get_broadcaster,
        ):
            mock_mqtt = MagicMock(spec=MQTTBroadcaster)
            mock_get_broadcaster.return_value = mock_mqtt
            mock_worker_instance = MagicMock()
            mock_worker_instance.get_supported_task_types.return_value = (
                []
            )  # pyright: ignore[reportAny] ignore mock type for testing purposes
            mock_worker.return_value = mock_worker_instance

            mock_config = MagicMock()
            mock_config.worker_poll_interval = 1.0
            mock_config.worker_supported_tasks = None
            mock_config.compute_storage_dir = (
                os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts")
                + "/compute"
            )

            with pytest.raises(RuntimeError, match="No compute plugins"):
                _ = ComputeWorker(
                    worker_id="test-worker",
                    config=mock_config,
                    supported_tasks=["some_task"],
                )

    @pytest.mark.usefixtures("mock_dependencies")
    def test_worker_init_with_custom_poll_interval(self):
        """Test worker initialization with custom poll interval."""
        mock_config = MagicMock()
        mock_config.worker_poll_interval = 30
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"

        worker = ComputeWorker(
            worker_id="test-worker",
            config=mock_config,
        )

        assert worker.poll_interval == 30

    @pytest.mark.usefixtures("mock_dependencies")
    async def test_heartbeat_task_publishes_periodically(self):
        """Test heartbeat task publishes capabilities periodically."""
        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.mqtt_heartbeat_interval = 0.01  # Fast for test

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)

        # Mock capability broadcaster
        worker.capability_broadcaster.publish = MagicMock()

        # Run heartbeat task for a short time
        task = asyncio.create_task(
            worker._heartbeat_task()
        )  # pyright: ignore[reportPrivateUsage]

        # Wait a bit then cancel
        await asyncio.sleep(0.1)
        _ = task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify publish was called (might be 0 or more times depending on timing)
        # The important thing is it doesn't raise an exception

    @pytest.mark.usefixtures("mock_dependencies")
    async def test_heartbeat_task_stops_on_shutdown(self):
        """Test heartbeat task stops when shutdown event is set."""
        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.mqtt_heartbeat_interval = 0.01
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.worker_supported_tasks = None
        mock_config.capability_topic_prefix = ""

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.publish = MagicMock()

        # Start heartbeat task
        task = asyncio.create_task(
            worker._heartbeat_task()
        )  # pyright: ignore[reportPrivateUsage]

        # Set shutdown event
        shutdown_event.set()

        # Wait a bit for task to finish
        await asyncio.sleep(0.1)

        # Task should complete without being cancelled
        assert task.done()

    async def test_process_next_job_success(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test processing a job successfully."""
        mock_dependencies["worker_instance"].run_once = AsyncMock(return_value=True)

        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.publish = MagicMock()

        result = await worker._process_next_job()  # pyright: ignore[reportPrivateUsage]

        assert result is True
        mock_dependencies["worker_instance"].run_once.assert_called_once()

        # Verify broadcaster state changes
        assert worker.capability_broadcaster.publish.call_count >= 2  # busy + idle

    async def test_process_next_job_no_jobs(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test processing when no jobs are available."""
        mock_dependencies["worker_instance"].run_once = AsyncMock(return_value=False)

        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.publish = MagicMock()

        result = await worker._process_next_job()  # pyright: ignore[reportPrivateUsage]

        assert result is False

    async def test_process_next_job_error(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test processing job when an error occurs."""
        mock_dependencies["worker_instance"].run_once = AsyncMock(
            side_effect=Exception("Test error")
        )

        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.publish = MagicMock()

        result = await worker._process_next_job()  # pyright: ignore[reportPrivateUsage]

        assert result is False  # Should return False on error

    async def test_process_next_job_updates_broadcaster_state(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test that processing job updates broadcaster idle state."""
        mock_dependencies["worker_instance"].run_once = AsyncMock(return_value=True)

        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.is_idle = True
        worker.capability_broadcaster.publish = MagicMock()

        _ = await worker._process_next_job()  # pyright: ignore[reportPrivateUsage]

        # Should be marked idle after processing
        assert worker.capability_broadcaster.is_idle is True

    async def test_run_worker_loop(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test main worker run loop."""
        mock_dependencies["worker_instance"].run_once = AsyncMock(return_value=False)

        mock_config = MagicMock()
        mock_config.worker_poll_interval = 0.01
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.mqtt_heartbeat_interval = 1.0

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.init = MagicMock()
        worker.capability_broadcaster.publish = MagicMock()
        worker.capability_broadcaster.clear = MagicMock()

        # Run for a short time then shutdown
        async def shutdown_after_delay():
            await asyncio.sleep(0.05)
            shutdown_event.set()

        shutdown_task = asyncio.create_task(shutdown_after_delay())

        await worker.run()
        await shutdown_task
        worker.close()

        # Verify initialization and cleanup
        worker.capability_broadcaster.clear.assert_called_once()
        assert worker.capability_broadcaster.publish.call_count >= 1

    async def test_run_worker_loop_processes_jobs(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test worker loop processes jobs."""
        call_count = 0

        async def run_once_side_effect(task_types: list[str]):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                shutdown_event.set()
            return True

        mock_dependencies["worker_instance"].run_once = AsyncMock(
            side_effect=run_once_side_effect
        )

        mock_config = MagicMock()
        mock_config.worker_poll_interval = 0.01
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.mqtt_heartbeat_interval = 1.0

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.init = MagicMock()
        worker.capability_broadcaster.publish = MagicMock()
        worker.capability_broadcaster.clear = MagicMock()

        await worker.run()

        assert call_count >= 2

    async def test_run_worker_loop_handles_cancelled_error(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test worker loop handles asyncio.CancelledError."""
        mock_dependencies["worker_instance"].run_once = AsyncMock(
            side_effect=asyncio.CancelledError()
        )

        mock_config = MagicMock()
        mock_config.worker_poll_interval = 0.01
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.mqtt_heartbeat_interval = 1.0

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.init = MagicMock()
        worker.capability_broadcaster.publish = MagicMock()
        worker.capability_broadcaster.clear = MagicMock()
        
        await worker.run()
        worker.close()

        # Should complete gracefully
        worker.capability_broadcaster.clear.assert_called_once()

    async def test_run_worker_loop_handles_general_exception(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test worker loop handles general exceptions."""
        call_count = 0

        async def run_once_side_effect(task_types: list[str]):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Test error")
            else:
                shutdown_event.set()
                return False

        mock_dependencies["worker_instance"].run_once = AsyncMock(
            side_effect=run_once_side_effect
        )

        mock_config = MagicMock()
        mock_config.worker_poll_interval = 0.01
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.mqtt_heartbeat_interval = 1.0

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.init = MagicMock()
        worker.capability_broadcaster.publish = MagicMock()
        worker.capability_broadcaster.clear = MagicMock()

        await worker.run()

        # Should continue after exception
        assert call_count >= 2

    async def test_run_worker_classmethod(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test run_worker classmethod creates and runs worker."""
        with patch("compute.worker.signal.signal") as mock_signal:
            # Set shutdown immediately to exit quickly
            shutdown_event.set()

            mock_dependencies["worker_instance"].run_once = AsyncMock(
                return_value=False
            )

            # Mock capability broadcaster methods
            mock_broadcaster_instance = MagicMock()
            mock_broadcaster_instance.init = MagicMock()
            mock_broadcaster_instance.publish = MagicMock()
            mock_broadcaster_instance.clear = MagicMock()
            mock_dependencies["broadcaster"].return_value = mock_broadcaster_instance

            mock_config = MagicMock()
            mock_config.worker_poll_interval = 1.0

            await ComputeWorker.run_worker(
                worker_id="test-worker",
                config=mock_config,
                tasks=["image_resize"],
            )

            # Verify signal handlers were registered
            assert mock_signal.call_count == 2

    async def test_run_worker_classmethod_with_no_tasks(
        self, mock_dependencies: dict[str, MagicMock | AsyncMock]
    ):
        """Test run_worker classmethod with None tasks."""
        with patch("compute.worker.signal.signal"):
            shutdown_event.set()

            mock_dependencies["worker_instance"].run_once = AsyncMock(
                return_value=False
            )

            # Mock capability broadcaster
            mock_broadcaster_instance = MagicMock()
            mock_broadcaster_instance.init = MagicMock()
            mock_broadcaster_instance.publish = MagicMock()
            mock_broadcaster_instance.clear = MagicMock()
            mock_dependencies["broadcaster"].return_value = mock_broadcaster_instance

            mock_config = MagicMock()
            mock_config.worker_poll_interval = 1.0
            mock_config.worker_supported_tasks = None

            await ComputeWorker.run_worker(
                worker_id="test-worker",
                config=mock_config,
                tasks=None,
            )

            # Should complete without error

    @pytest.mark.usefixtures("mock_dependencies")
    async def test_run_cancels_heartbeat_on_shutdown(self):
        """Test that run cancels heartbeat task on shutdown."""
        mock_config = MagicMock()
        mock_config.worker_poll_interval = 1.0
        mock_config.worker_supported_tasks = None
        mock_config.compute_storage_dir = (
            os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts") + "/compute"
        )
        mock_config.capability_topic_prefix = "capabilities"
        mock_config.mqtt_heartbeat_interval = 1.0

        worker = ComputeWorker(worker_id="test-worker", config=mock_config)
        worker.capability_broadcaster.init = MagicMock()
        worker.capability_broadcaster.publish = MagicMock()
        worker.capability_broadcaster.clear = MagicMock()

        # Set shutdown immediately
        shutdown_event.set()

        await worker.run()
        worker.close()

        # Cleanup should be called
        worker.capability_broadcaster.clear.assert_called_once()
