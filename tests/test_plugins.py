import pytest
from unittest.mock import MagicMock, patch

from compute.config import ComputeServerConfig
from compute.plugins import create_compute_plugin_router


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = MagicMock(spec=ComputeServerConfig)
    config.compute_storage_dir = "/tmp/compute_storage"
    return config


class TestCreateComputePluginRouter:
    """Tests for create_compute_plugin_router function."""

    def test_create_compute_plugin_router(self, mock_config):
        """Test creating plugin router."""
        with patch("compute.plugins.create_master_router") as mock_create_router:
            with patch("compute.plugins.JobRepositoryService") as mock_repo:
                with patch("compute.plugins.JobStorageService"):
                    mock_router = MagicMock()
                    mock_create_router.return_value = mock_router
                    mock_repository = MagicMock()
                    mock_repo.return_value = mock_repository

                    router, repository = create_compute_plugin_router(mock_config)

                    assert router == mock_router
                    assert repository == mock_repository

                    # Verify create_master_router was called with correct args
                    mock_create_router.assert_called_once()
                    call_kwargs = mock_create_router.call_args[1]  # pyright: ignore[reportAny] for testing purposes
                    assert "repository" in call_kwargs
                    assert "file_storage" in call_kwargs
                    assert "get_current_user" in call_kwargs

    def test_create_compute_plugin_router_uses_session_local(self, mock_config):
        """Test that plugin router uses SessionLocal."""
        with patch("compute.plugins.create_master_router") as mock_create_router:
            with patch("compute.plugins.JobRepositoryService") as mock_repo:
                with patch("compute.plugins.JobStorageService"):
                    with patch("compute.plugins.SessionLocal") as mock_session:
                        mock_router = MagicMock()
                        mock_create_router.return_value = mock_router

                        _ = create_compute_plugin_router(mock_config)

                        # Verify JobRepositoryService was initialized with SessionLocal
                        mock_repo.assert_called_once_with(mock_session, mock_config)

    def test_create_compute_plugin_router_uses_compute_storage_dir(self, mock_config):
        """Test that plugin router uses COMPUTE_STORAGE_DIR."""
        mock_config.compute_storage_dir = "/test/storage"
        
        with patch("compute.plugins.create_master_router") as mock_create_router:
            with patch("compute.plugins.JobRepositoryService"):
                with patch("compute.plugins.JobStorageService") as mock_storage:
                    mock_router = MagicMock()
                    mock_create_router.return_value = mock_router

                    _ = create_compute_plugin_router(mock_config)

                    # Verify JobStorageService was initialized with correct base_dir
                    mock_storage.assert_called_once_with(base_dir="/test/storage")

    def test_create_compute_plugin_router_uses_auth_permission(self, mock_config):
        """Test that plugin router requires ai_inference_support permission."""
        with patch("compute.plugins.create_master_router") as mock_create_router:
            with patch("compute.plugins.JobRepositoryService"):
                with patch("compute.plugins.JobStorageService"):
                    with patch("compute.plugins.require_permission") as mock_require_permission:
                        mock_router = MagicMock()
                        mock_create_router.return_value = mock_router
                        mock_permission_checker = MagicMock()
                        mock_require_permission.return_value = mock_permission_checker

                        _ = create_compute_plugin_router(mock_config)

                        # Verify require_permission was called with correct permission
                        mock_require_permission.assert_called_once_with("ai_inference_support")

                        # Verify the permission checker was passed to create_master_router
                        call_kwargs = mock_create_router.call_args[1]  # pyright: ignore[reportAny] for testing purposes
                        assert call_kwargs["get_current_user"] == mock_permission_checker
