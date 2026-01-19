from __future__ import annotations

import asyncio
import os
from typing import Annotated, ClassVar, Literal

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from .database import get_db

# ─────────────────────────────────────
# Permissions
# ─────────────────────────────────────

Permission = Literal[
    "ai_inference_support",
    "admin",
]

Permissions = Annotated[list[str], Field(default_factory=list)]


# ─────────────────────────────────────
# JWT payload model
# ─────────────────────────────────────


class UserPayload(BaseModel):
    """JWT token payload for authenticated users."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="ignore",
        strict=True,
    )

    id: str
    is_admin: bool = Field(default=False, strict=True)
    permissions: Permissions

    @field_validator("permissions")
    @classmethod
    def unique_permissions(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


# ─────────────────────────────────────
# OAuth2
# ─────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="auth/token",
    auto_error=False,
)


# ─────────────────────────────────────
# Public key loader (cached)
# ─────────────────────────────────────

_public_key_cache: str | None = None
_max_load_attempts: int = 30  # ~30 seconds


async def get_public_key(public_key_path: str) -> str:
    """Load and cache the public key with retry during startup."""

    global _public_key_cache

    if _public_key_cache:
        return _public_key_cache

    for attempt in range(_max_load_attempts):
        if os.path.exists(public_key_path):
            try:
                with open(public_key_path) as f:
                    key = f.read().strip()
                    if key:
                        _public_key_cache = key
                        return key
            except OSError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to read public key file: {exc}",
                )

        if attempt < _max_load_attempts - 1:
            await asyncio.sleep(1)

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Public key not found at {public_key_path}. "
        + "Is the authentication service running?",
    )


# ─────────────────────────────────────
# Current user dependency
# ─────────────────────────────────────


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserPayload | None:
    """Validate the JWT and return the user payload."""

    from .config_service import ConfigService

    # Check request state config first (env/CLI override)
    # If auth is disabled at system level, we skip auth
    if request.app.state.config.auth_disabled:
        return None

    # Check runtime config (database override)
    config_service = ConfigService(db)
    if not config_service.get_auth_enabled():  # auth_enabled=false → guest mode ON
        return None

    if token is None:
        return None

    public_key = await get_public_key(request.app.state.config.public_key_path)

    try:
        raw = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            options={"require": ["id", "exp"]},
        )
        return UserPayload.model_validate(raw)

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT payload is invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─────────────────────────────────────
# Permission dependencies
# ─────────────────────────────────────


def require_permission(permission: Permission):
    """Require a specific permission."""

    async def permission_checker(
        request: Request,
        current_user: UserPayload | None = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> UserPayload | None:
        from .config_service import ConfigService

        # Check system config
        if request.app.state.config.auth_disabled:
            return current_user

        # Check runtime config
        config_service = ConfigService(db)
        if not config_service.get_auth_enabled():  # auth_enabled=false → guest mode ON
            return current_user

        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if current_user.is_admin:
            return current_user

        if permission not in current_user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}",
            )

        return current_user

    return permission_checker


async def require_admin(
    request: Request,
    current_user: UserPayload | None = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPayload | None:
    from .config_service import ConfigService

    # Check system config
    if request.app.state.config.auth_disabled:
        return current_user

    # Check runtime config
    config_service = ConfigService(db)
    if not config_service.get_auth_enabled():  # auth_enabled=false → guest mode ON
        return current_user

    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin access required",
        )

    return current_user

