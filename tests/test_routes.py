"""Tests for API routes."""

import os
from collections.abc import Generator
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from cl_ml_tools import MQTTBroadcaster
from compute.models import Base, Job
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from compute.auth import UserPayload
from compute.routes import router
from compute.schemas import (
    CapabilityStats,
    CleanupResult,
    JobResponse,
    StorageInfo,
    WorkerCapabilitiesResponse,
    PrefResponse,
)


@pytest.fixture(autouse=True)
def mock_broadcaster():
    """Mock JobStatusBroadcaster and get_broadcaster for all tests."""
    with patch("cl_ml_tools.get_broadcaster") as mock_get_broadcaster:
        mock_get_broadcaster.return_value = MagicMock(spec=MQTTBroadcaster)
        yield


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    test_app = FastAPI()
    test_app.include_router(router)
    
    # Inject mock config
    mock_config = MagicMock()
    mock_config.auth_disabled = False
    mock_config.public_key_path = os.path.join(os.getenv("TEST_ARTIFACT_DIR", "/tmp/cl_server_test_artifacts"), "compute", "public_key")
    mock_config.mqtt_url = "mqtt://mock-broker:1883"
    mock_config.capability_topic_prefix = "inference/workers"
    mock_config.mqtt_job_events_topic = "inference/events"
    test_app.state.config = mock_config
    
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user() -> UserPayload:
    """Create mock authenticated user."""
    return UserPayload(
        id="test_user",
        is_admin=False,
        permissions=["ai_inference_support"],
    )


@pytest.fixture
def mock_admin() -> UserPayload:
    """Create mock admin user."""
    return UserPayload(
        id="admin_user",
        is_admin=True,
        permissions=["admin", "ai_inference_support"],
    )


class TestGetJob:
    """Tests for GET /jobs/{job_id} endpoint."""

    def test_get_job_success(self, client: TestClient, db_session: Session):
        """Test getting a job successfully."""
        from compute.database import get_db
        from compute.dependencies import get_mqtt_broadcaster

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_mqtt_broadcaster] = lambda: None

        # Mock JobService.get_job to return a JobResponse
        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = False
            with patch("compute.service.JobService.get_job") as mock_get_job:
                mock_get_job.return_value = JobResponse(
                    job_id="test-job-1",
                    task_type="test_task",
                    status="queued",
                    progress=0,
                    params={"key": "value"},
                    task_output={},
                    created_at=1234567890000,
                    updated_at=1234567890000,
                    priority=5,
                    error_message=None,
                    started_at=None,
                    completed_at=None,
                )

                response = client.get("/jobs/test-job-1")

                assert response.status_code == 200
                data = JobResponse.model_validate(response.json())
                assert data.job_id == "test-job-1"
                assert data.task_type == "test_task"
                assert data.status == "queued"

                # Clean up
                app.dependency_overrides.clear()

    def test_get_job_not_found(self, client: TestClient, db_session: Session):
        """Test getting a non-existent job."""
        from fastapi import HTTPException

        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db

        from compute.dependencies import get_mqtt_broadcaster
        app.dependency_overrides[get_mqtt_broadcaster] = lambda: None

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = False
            with patch("compute.service.JobService.get_job") as mock_get_job:
                # Simulate job not found by raising HTTPException
                mock_get_job.side_effect = HTTPException(
                    status_code=404, detail="Job test-job-1 not found"
                )

                response = client.get("/jobs/test-job-1")

                assert response.status_code == 404

                # Clean up
                app.dependency_overrides.clear()

    def test_get_job_requires_auth(self, client: TestClient, db_session: Session):
        """Test that get_job requires authentication."""
        from fastapi import HTTPException

        from compute.auth import require_permission
        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db

        def mock_auth():
            raise HTTPException(status_code=401, detail="Authentication required")

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True
            app.dependency_overrides[require_permission("ai_inference_support")] = mock_auth

            response = client.get("/jobs/test-job-1")

            assert response.status_code == 401


class TestDeleteJob:
    """Tests for DELETE /jobs/{job_id} endpoint."""

    def test_delete_job_success(self, client: TestClient, db_session: Session):
        """Test deleting a job successfully."""
        # Create test job
        job = Job(
            job_id="test-job-2",
            task_type="test_task",
            status="completed",
            progress=100,
            params={},
            output={},
            created_at=1234567890000,
            priority=5,
        )
        db_session.add(job)
        db_session.commit()

        from compute.database import get_db

        def override_get_db():
            yield db_session

        # Mock the repository and file storage
        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = False
            with patch("compute.service.JobRepositoryService") as mock_repo_class:
                with patch("compute.service.JobStorageService"):
                    mock_repo = MagicMock()
                    mock_repo.get_job.return_value = job  # pyright: ignore[reportAny] ignore mock types for testing purposes
                    mock_repo.delete_job.return_value = None  # pyright: ignore[reportAny] ignore mock types for testing purposes
                    mock_repo_class.return_value = mock_repo

                    app = cast(FastAPI, client.app)
                    app.dependency_overrides[get_db] = override_get_db
                    
                    from compute.dependencies import get_mqtt_broadcaster
                    app.dependency_overrides[get_mqtt_broadcaster] = lambda: None

                    response = client.delete("/jobs/test-job-2")

                    assert response.status_code == 204

                    # Clean up
                    app = cast(FastAPI, client.app)
                    app.dependency_overrides.clear()

    def test_delete_job_not_found(self, client: TestClient, db_session: Session):
        """Test deleting a non-existent job."""
        from compute.database import get_db

        def override_get_db():
            yield db_session

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = False
            with patch("compute.service.JobRepositoryService") as mock_repo_class:
                mock_repo = MagicMock()
                mock_repo.get_job.return_value = None  # pyright: ignore[reportAny] ignore mock types for testing purposes
                mock_repo_class.return_value = mock_repo

                app = cast(FastAPI, client.app)
                app.dependency_overrides[get_db] = override_get_db
                
                from compute.dependencies import get_mqtt_broadcaster
                app.dependency_overrides[get_mqtt_broadcaster] = lambda: None

                response = client.delete("/jobs/nonexistent-job")

                assert response.status_code == 404

                # Clean up
                app = cast(FastAPI, client.app)
                app.dependency_overrides.clear()


class TestGetStorageSize:
    """Tests for GET /admin/jobs/storage/size endpoint."""

    def test_get_storage_size_success(
        self, client: TestClient, db_session: Session, mock_admin: UserPayload
    ):
        """Test getting storage size as admin."""
        from compute.auth import require_admin
        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_admin] = lambda: mock_admin

        with patch("compute.service.JobService.get_storage_size") as mock_get_storage:
            mock_get_storage.return_value = StorageInfo(
                total_size=1024000,
                job_count=42,
            )

            response = client.get("/admin/jobs/storage/size")

            assert response.status_code == 200
            data = StorageInfo.model_validate(response.json())
            assert data.total_size == 1024000
            assert data.job_count == 42

    def test_get_storage_size_requires_admin(self, client: TestClient, db_session: Session):
        """Test that storage size endpoint requires admin."""
        from fastapi import HTTPException

        from compute.auth import require_admin
        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db

        def mock_admin_check():
            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[require_admin] = mock_admin_check

        response = client.get("/admin/jobs/storage/size")

        assert response.status_code == 403


class TestCleanupOldJobs:
    """Tests for DELETE /admin/jobs/cleanup endpoint."""

    def test_cleanup_old_jobs_success(
        self, client: TestClient, db_session: Session, mock_admin: UserPayload
    ):
        """Test cleanup old jobs as admin."""
        from compute.auth import require_admin
        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_admin] = lambda: mock_admin

        with patch("compute.service.JobService.cleanup_old_jobs") as mock_cleanup:
            mock_cleanup.return_value = CleanupResult(
                deleted_count=10,
                freed_space=5242880,
            )

            response = client.delete("/admin/jobs/cleanup?days=7")

            assert response.status_code == 200
            data = CleanupResult.model_validate(response.json())
            assert data.deleted_count == 10
            assert data.freed_space == 5242880

    def test_cleanup_old_jobs_custom_days(
        self, client: TestClient, db_session: Session, mock_admin: UserPayload
    ):
        """Test cleanup with custom days parameter."""
        from compute.auth import require_admin
        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_admin] = lambda: mock_admin

        with patch("compute.service.JobService.cleanup_old_jobs") as mock_cleanup:
            mock_cleanup.return_value = CleanupResult(
                deleted_count=5,
                freed_space=1024000,
            )

            response = client.delete("/admin/jobs/cleanup?days=30")

            assert response.status_code == 200
            mock_cleanup.assert_called_once_with(30)

    def test_cleanup_old_jobs_requires_admin(self, client: TestClient, db_session: Session):
        """Test that cleanup endpoint requires admin."""
        from fastapi import HTTPException

        from compute.auth import require_admin
        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db

        def mock_admin_check():
            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[require_admin] = mock_admin_check

        response = client.delete("/admin/jobs/cleanup?days=7")

        assert response.status_code == 403


class TestGetWorkerCapabilities:
    """Tests for GET /capabilities endpoint."""

    def test_get_worker_capabilities_success(self, client: TestClient, db_session: Session):
        """Test getting worker capabilities."""
        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db

        with patch("compute.service.CapabilityService.get_available_capabilities") as mock_get_caps:
            with patch("compute.service.CapabilityService.get_worker_count") as mock_get_count:
                mock_get_caps.return_value = CapabilityStats(
                    root={
                        "image_resize": 2,
                        "image_conversion": 1,
                    }
                )
                mock_get_count.return_value = 3

                response = client.get("/capabilities")

                assert response.status_code == 200
                data = WorkerCapabilitiesResponse.model_validate(response.json())
                assert data.num_workers == 3
                assert data.capabilities.root["image_resize"] == 2
                assert data.capabilities.root["image_conversion"] == 1

    def test_get_worker_capabilities_no_workers(self, client: TestClient, db_session: Session):
        """Test getting capabilities when no workers available."""
        from compute.database import get_db

        app = cast(FastAPI, client.app)
        def override_get_db():
            yield db_session
        app.dependency_overrides[get_db] = override_get_db

        with patch("compute.service.CapabilityService.get_available_capabilities") as mock_get_caps:
            with patch("compute.service.CapabilityService.get_worker_count") as mock_get_count:
                mock_get_caps.return_value = CapabilityStats(root={})
                mock_get_count.return_value = 0

                response = client.get("/capabilities")

                assert response.status_code == 200
                data = WorkerCapabilitiesResponse.model_validate(response.json())
                assert data.num_workers == 0
                assert data.capabilities.root == {}
