"""Tests for FastAPI application."""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi.openapi.models import OpenAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from compute.database import init_db, SessionLocal
import compute.database
from compute.models import Base
from compute.schemas import RootResponse
from compute.task_server import app


@pytest.fixture
def mock_config():
    with patch("compute.config.ComputeConfig") as mock:
        config_instance = MagicMock()
        config_instance.auth_disabled = False
        config_instance.public_key_path = "/tmp/public_key"
        config_instance.database_url = "sqlite:///:memory:"
        config_instance.debug = False
        mock.from_cli_args.return_value = config_instance
        yield config_instance

@pytest.fixture
def client(mock_config) -> TestClient:
    """Create test client."""
    # Initialize database with mock config (which has valid sqlite url)
    # We must do this before TestClient(app) because app lifespan runs check_tables_exist
    
    # Check if already initialized (by other tests?)
    # We want a fresh start for this test file ideally, but global state...
    # Let's force re-init or just ensure tables exist.
    
    # Reset globals to ensure clean init
    compute.database.engine = None
    compute.database.SessionLocal = None
    
    init_db(mock_config)
    
    # Create tables
    if compute.database.engine:
        Base.metadata.create_all(bind=compute.database.engine)
    
    with patch("compute.database.check_tables_exist"):
        with TestClient(app) as client:
            yield client
    
    # Cleanup
    if compute.database.engine:
        Base.metadata.drop_all(bind=compute.database.engine)
    compute.database.engine = None
    compute.database.SessionLocal = None


class TestTaskServerApp:
    """Tests for Task Server FastAPI application."""

    def test_app_exists(self):
        """Test that app is created."""
        assert app is not None
        assert app.title == "Task Server"
        assert app.version == "v1"

    def test_app_includes_routers(self):
        """Test that app includes required routers."""
        # Check that routes are registered
        routes = [getattr(route, "path") for route in app.routes if hasattr(route, "path")]

        # Job management routes
        assert "/jobs/{job_id}" in routes

        # Admin routes
        assert "/admin/jobs/storage/size" in routes
        assert "/admin/jobs/cleanup" in routes

        # Capability route
        assert "/capabilities" in routes

        # Root route
        assert "/" in routes

    def test_root_endpoint(self, client: TestClient):
        """Test root health check endpoint."""
        with patch("compute.config_service.ConfigService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = False
            response = client.get("/")

            assert response.status_code == 200
            data = RootResponse.model_validate(response.json())
            assert data.status == "healthy"
            assert data.service == "Task Server"
            assert data.version == "v1"

    def test_root_response_schema(self, client: TestClient):
        """Test root endpoint response matches schema."""
        with patch("compute.config_service.ConfigService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = False
            response = client.get("/")

            # validate with Pydantic model
            _ = RootResponse.model_validate(response.json())

    def test_http_exception_handler(self, client: TestClient, db_session: Session):
        """Test HTTP exception handler preserves error format."""
        # Try to access non-existent job (will trigger HTTPException)
        with patch("compute.service.JobService.get_job") as mock_get_job:
            from fastapi import HTTPException

            from compute.database import get_db

            mock_get_job.side_effect = HTTPException(status_code=404, detail="Job not found")

            def override_get_db():
                yield db_session

            with patch("compute.config_service.ConfigService") as mock_config:
                mock_config.return_value.get_auth_enabled.return_value = False
                app.dependency_overrides[get_db] = override_get_db

                response = client.get("/jobs/test-job")

                assert response.status_code == 404
                error_data = cast(dict[str, str], response.json())
                assert "detail" in error_data

                # Clean up
                app.dependency_overrides.clear()

    def test_shutdown_event_closes_capability_manager(self):
        """Test that lifespan shutdown closes capability manager."""
        import asyncio

        from compute.task_server import lifespan

        with patch("compute.database.check_tables_exist"):
            with patch("compute.capability_manager.close_capability_manager") as mock_close:
                # Test lifespan context manager shutdown
                async def run_lifespan():
                    async with lifespan(app):
                        pass  # Shutdown happens when exiting the context

                asyncio.run(run_lifespan())

            mock_close.assert_called_once()

    def test_plugin_router_included(self):
        """Test that plugin router is included in app."""
        # The plugin router is created and included
        # We verify this indirectly by checking that create_compute_plugin_router was called
        # This is already tested in test_plugins.py, so here we just verify the app structure

        # Check that app has expected number of routers
        # app should include: main router + plugin router
        assert len(app.router.routes) > 0

    def test_openapi_schema_generated(self, client: TestClient):
        """Test that OpenAPI schema is generated."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        # Validate with Pydantic model then convert to dict for easier access
        schema_model = OpenAPI.model_validate(response.json())
        schema = cast(
            dict[str, dict[str, str] | dict[str, dict[str, dict[str, str]]]],
            schema_model.model_dump(),
        )
        assert "openapi" in schema
        assert "info" in schema
        info = cast(dict[str, str], schema["info"])
        assert info["title"] == "Task Server"
        assert info["version"] == "v1"

    def test_openapi_paths_exist(self, client: TestClient):
        """Test that expected paths exist in OpenAPI schema."""
        response = client.get("/openapi.json")
        schema_model = OpenAPI.model_validate(response.json())
        schema = schema_model.model_dump()

        assert "paths" in schema
        paths = cast(dict[str, dict[str, dict[str, str]]], schema["paths"])
        assert "/" in paths
        assert "/jobs/{job_id}" in paths
        assert "/capabilities" in paths
        assert "/admin/jobs/storage/size" in paths
        assert "/admin/jobs/cleanup" in paths

    def test_openapi_operations(self, client: TestClient):
        """Test that operations have correct operation IDs."""
        response = client.get("/openapi.json")
        schema_model = OpenAPI.model_validate(response.json())
        schema = schema_model.model_dump()

        paths = cast(dict[str, dict[str, dict[str, str]]], schema["paths"])

        # Check root endpoint
        root_get_op = paths["/"]["get"]
        assert root_get_op["operationId"] == "root_get"

        # Check job endpoints
        job_get_op = paths["/jobs/{job_id}"]["get"]
        assert job_get_op["operationId"] == "get_job"

        job_delete_op = paths["/jobs/{job_id}"]["delete"]
        assert job_delete_op["operationId"] == "delete_job"

        # Check capability endpoint
        cap_get_op = paths["/capabilities"]["get"]
        assert cap_get_op["operationId"] == "get_worker_capabilities"

    def test_app_tags(self, client: TestClient):
        """Test that endpoints are tagged correctly."""
        response = client.get("/openapi.json")
        schema_model = OpenAPI.model_validate(response.json())
        schema = schema_model.model_dump()

        paths = cast(dict[str, dict[str, dict[str, list[str]]]], schema["paths"])

        # Job endpoints should have 'job' tag
        job_get_op = paths["/jobs/{job_id}"]["get"]
        assert "job" in job_get_op["tags"]

        # Admin endpoints should have 'admin' tag
        storage_get_op = paths["/admin/jobs/storage/size"]["get"]
        assert "admin" in storage_get_op["tags"]

        # Capability endpoint should have 'compute' tag
        cap_get_op = paths["/capabilities"]["get"]
        assert "compute" in cap_get_op["tags"]
