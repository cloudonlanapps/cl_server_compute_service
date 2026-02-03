"""Tests for authentication and authorization."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError

from compute.auth import (
    UserPayload,
    get_current_user,
    get_public_key,
    require_admin,
    require_permission,
)


@pytest.fixture
def mock_db():
    """Mock database session for tests."""
    return MagicMock()


class TestUserPayload:
    """Tests for UserPayload model."""

    def test_user_payload_valid(self):
        """Test UserPayload with valid data."""
        user = UserPayload(
            id="user123",
            is_admin=False,
            permissions=["ai_inference_support"],
        )

        assert user.id == "user123"
        assert user.is_admin is False
        assert user.permissions == ["ai_inference_support"]

    def test_user_payload_admin(self):
        """Test UserPayload for admin user."""
        user = UserPayload(
            id="admin123",
            is_admin=True,
            permissions=["admin", "ai_inference_support"],
        )

        assert user.id == "admin123"
        assert user.is_admin is True
        assert "admin" in user.permissions

    def test_user_payload_defaults(self):
        """Test UserPayload default values."""
        user = UserPayload(id="user456", permissions=[])

        assert user.id == "user456"
        assert user.is_admin is False
        assert user.permissions == []

    def test_user_payload_unique_permissions(self):
        """Test that duplicate permissions are removed."""
        user = UserPayload(
            id="user789",
            permissions=[
                "ai_inference_support",
                "admin",
                "ai_inference_support",  # duplicate
            ],
        )

        # unique_permissions validator should remove duplicates
        assert len(user.permissions) == 2
        assert "ai_inference_support" in user.permissions
        assert "admin" in user.permissions

    def test_user_payload_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        user = UserPayload.model_validate(
            {
                "id": "user999",
                "permissions": [],
                "extra_field": "ignored",
            }
        )

        assert user.id == "user999"
        assert not hasattr(user, "extra_field")

    def test_user_payload_missing_required_field(self):
        """Test that missing required field raises ValidationError."""
        with pytest.raises(ValidationError):
            _ = UserPayload.model_validate({"permissions": []})


class TestGetPublicKey:
    """Tests for get_public_key function."""

    @pytest.mark.asyncio
    async def test_get_public_key_success(self):
        """Test successful public key loading."""
        test_key = "-----BEGIN PUBLIC KEY-----\ntest_key\n-----END PUBLIC KEY-----"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            _ = tmp.write(test_key)
            tmp_path = tmp.name

        try:
            # Clear cache
            import compute.auth

            compute.auth._public_key_cache = None  # pyright: ignore[reportPrivateUsage] for testing purposes

            key = await get_public_key(tmp_path)
            assert key == test_key

            # Test caching - should return same value without file access
            key2 = await get_public_key(tmp_path)
            assert key2 == test_key
        finally:
            os.unlink(tmp_path)
            # Reset cache
            import compute.auth

            compute.auth._public_key_cache = None  # pyright: ignore[reportPrivateUsage] for testing purposes

    @pytest.mark.asyncio
    async def test_get_public_key_file_not_found(self):
        """Test public key loading when file doesn't exist."""
        nonexistent_path = "/nonexistent/path/to/key.pem"

        with patch("compute.auth._max_load_attempts", 2):  # Speed up test
            # Clear cache
            import compute.auth

            compute.auth._public_key_cache = None  # pyright: ignore[reportPrivateUsage] for testing purposes

            with pytest.raises(HTTPException) as exc_info:
                _ = await get_public_key(nonexistent_path)

            assert exc_info.value.status_code == 500
            assert "Public key not found" in exc_info.value.detail

        # Reset cache
        import compute.auth

        compute.auth._public_key_cache = None  # pyright: ignore[reportPrivateUsage] for testing purposes

    @pytest.mark.asyncio
    async def test_get_public_key_empty_file(self):
        """Test public key loading with empty file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            _ = tmp.write("")  # Empty file
            tmp_path = tmp.name

        try:
            with patch("compute.auth._max_load_attempts", 2):
                # Clear cache
                import compute.auth

                compute.auth._public_key_cache = None  # pyright: ignore[reportPrivateUsage] for testing purposes

                with pytest.raises(HTTPException) as exc_info:
                    _ = await get_public_key(tmp_path)

                assert exc_info.value.status_code == 500
        finally:
            os.unlink(tmp_path)
            # Reset cache
            import compute.auth

            compute.auth._public_key_cache = None  # pyright: ignore[reportPrivateUsage] for testing purposes


class TestGetCurrentUser:
    """Tests for get_current_user function."""

    @pytest.mark.asyncio
    async def test_get_current_user_auth_disabled(self, mock_db):
        """Test get_current_user when auth is disabled (guest mode via CLI/system)."""
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = True
        
        user = await get_current_user(request=mock_request, token="any-token", db=mock_db)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_runtime_auth_disabled(self, mock_db):
        """Test get_current_user when auth is disabled (guest mode via runtime config)."""
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False
        
        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_pref.return_value = "true" 
            mock_config.return_value.get_auth_enabled.return_value = False  # Guest mode
            user = await get_current_user(request=mock_request, token="any-token", db=mock_db)
            assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self, mock_db):
        """Test get_current_user with no token provided."""
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            user = await get_current_user(request=mock_request, token=None, db=mock_db)
            assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self, mock_db):
        """Test get_current_user with valid JWT token."""
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        # Generate test key pair
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        public_key = private_key.public_key()

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        # Create valid JWT
        payload = {
            "id": "test_user",
            "is_admin": False,
            "permissions": ["ai_inference_support"],
        }
        token = jwt.encode(payload, private_pem, algorithm="ES256")

        token = jwt.encode(payload, private_pem, algorithm="ES256")

        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False
        mock_request.app.state.config.public_key_path = "/path/to/key.pem"

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            with patch("compute.auth.get_public_key", return_value=public_pem):
                user = await get_current_user(request=mock_request, token=token, db=mock_db)

                assert user is not None
                assert user.id == "test_user"
                assert user.is_admin is False
                assert "ai_inference_support" in user.permissions

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, mock_db):
        """Test get_current_user with invalid token."""
        public_key = "-----BEGIN PUBLIC KEY-----\nfake_key\n-----END PUBLIC KEY-----"

        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False
        mock_request.app.state.config.public_key_path = "/path/to/key.pem"

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            with patch("compute.auth.get_public_key", return_value=public_key):
                with pytest.raises(HTTPException) as exc_info:
                    _ = await get_current_user(request=mock_request, token="invalid.token.here", db=mock_db)

                assert exc_info.value.status_code == 401
                assert "Could not validate credentials" in exc_info.value.detail


class TestRequirePermission:
    """Tests for require_permission function."""

    @pytest.mark.asyncio
    async def test_require_permission_auth_disabled(self, mock_db):
        """Test permission check when auth is disabled (guest mode)."""
        checker = require_permission("ai_inference_support")
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = True

        result = await checker(request=mock_request, current_user=None, db=mock_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_require_permission_no_user(self, mock_db):
        """Test permission check when no user is authenticated."""
        checker = require_permission("ai_inference_support")
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            with pytest.raises(HTTPException) as exc_info:
                _ = await checker(request=mock_request, current_user=None, db=mock_db)

            assert exc_info.value.status_code == 401
            assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_permission_admin_user(self, mock_db):
        """Test that admin users have all permissions."""
        checker = require_permission("ai_inference_support")
        admin_user = UserPayload(
            id="admin",
            is_admin=True,
            permissions=[],
        )

        admin_user = UserPayload(
            id="admin",
            is_admin=True,
            permissions=[],
        )
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            result = await checker(request=mock_request, current_user=admin_user, db=mock_db)
            assert result == admin_user

    @pytest.mark.asyncio
    async def test_require_permission_user_has_permission(self, mock_db):
        """Test user with required permission."""
        checker = require_permission("ai_inference_support")
        user = UserPayload(
            id="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )

        user = UserPayload(
            id="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            result = await checker(request=mock_request, current_user=user, db=mock_db)
            assert result == user

    @pytest.mark.asyncio
    async def test_require_permission_user_missing_permission(self, mock_db):
        """Test user without required permission."""
        checker = require_permission("admin")
        user = UserPayload(
            id="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )

        user = UserPayload(
            id="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            with pytest.raises(HTTPException) as exc_info:
                _ = await checker(request=mock_request, current_user=user, db=mock_db)

            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in exc_info.value.detail
            assert "admin" in exc_info.value.detail


class TestRequireAdmin:
    """Tests for require_admin function."""

    @pytest.mark.asyncio
    async def test_require_admin_auth_disabled(self, mock_db):
        """Test admin check when auth is disabled (guest mode)."""
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = True
        
        result = await require_admin(request=mock_request, current_user=None, db=mock_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_require_admin_no_user(self, mock_db):
        """Test admin check when no user is authenticated."""
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            with pytest.raises(HTTPException) as exc_info:
                _ = await require_admin(request=mock_request, current_user=None, db=mock_db)

            assert exc_info.value.status_code == 401
            assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_admin_admin_user(self, mock_db):
        """Test admin check with admin user."""
        admin_user = UserPayload(
            id="admin",
            is_admin=True,
            permissions=["admin"],
        )

        admin_user = UserPayload(
            id="admin",
            is_admin=True,
            permissions=["admin"],
        )
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            result = await require_admin(request=mock_request, current_user=admin_user, db=mock_db)
            assert result == admin_user

    @pytest.mark.asyncio
    async def test_require_admin_non_admin_user(self, mock_db):
        """Test admin check with non-admin user."""
        user = UserPayload(
            id="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )

        user = UserPayload(
            id="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )
        mock_request = MagicMock()
        mock_request.app.state.config.auth_disabled = False

        with patch("compute.config_service.ServerPrefService") as mock_config:
            mock_config.return_value.get_auth_enabled.return_value = True  # Auth required
            with pytest.raises(HTTPException) as exc_info:
                _ = await require_admin(request=mock_request, current_user=user, db=mock_db)

            assert exc_info.value.status_code == 403
            assert "Admin access required" in exc_info.value.detail
