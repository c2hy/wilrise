"""JWT creation/verification and get_current_user dependency."""
# pyright: reportUnknownMemberType=false

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from starlette.requests import Request
from wilrise.errors import RpcError

from .database import get_db_session, get_user_by_username
from .models import UserRole, UserStatus

SECRET_KEY = os.environ.get("JWT_SECRET", "example-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    """Hash password for storage (bcrypt accepts at most 72 bytes)."""
    raw = password.encode("utf-8")
    if len(raw) > 72:
        raw = raw[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against hash (plain truncated to 72 bytes like hash)."""
    raw = plain.encode("utf-8")
    if len(raw) > 72:
        raw = raw[:72]
    return bcrypt.checkpw(raw, hashed.encode("ascii"))


def create_access_token(sub: str, expires_delta: timedelta | None = None) -> str:
    """Create JWT with subject (username)."""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {"sub": sub, "exp": expire, "type": "access"}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token() -> str:
    """Create a secure random refresh token."""
    return secrets.token_urlsafe(32)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate JWT; raise RpcError on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise RpcError(-32001, "Invalid token type", data={"code": "invalid_token_type"})
        return payload
    except jwt.ExpiredSignatureError:
        raise RpcError(-32001, "Token expired", data={"code": "token_expired"}) from None
    except jwt.InvalidTokenError:
        raise RpcError(-32001, "Invalid token", data={"code": "invalid_token"}) from None


def get_current_user(request: Request) -> dict[str, Any]:
    """Require valid JWT and return user dict; raise RpcError if unauthorized."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise RpcError(
            -32001,
            "Missing or invalid Authorization header",
            data={"code": "unauthorized"},
        )
    token = auth[7:].strip()
    payload = decode_access_token(token)
    sub = payload.get("sub")
    if not sub:
        raise RpcError(-32001, "Invalid token payload", data={"code": "invalid_token"})
    gen = get_db_session(request)
    try:
        session = next(gen)
        user = get_user_by_username(session, str(sub))
        if not user:
            raise RpcError(-32001, "User not found", data={"code": "user_not_found"})
        if user.status != UserStatus.ACTIVE:
            raise RpcError(-32001, "User account is not active", data={"code": "account_inactive"})
        return user.to_dict()
    finally:
        gen.close()


def get_current_active_user(request: Request) -> dict[str, Any]:
    """Get current user and verify account is active."""
    user = get_current_user(request)
    if user.get("status") != UserStatus.ACTIVE.value:
        raise RpcError(-32001, "User account is not active", data={"code": "account_inactive"})
    return user


def require_role(*roles: UserRole):
    """Decorator factory to require specific roles for access.

    Usage: require_role(UserRole.ADMIN)(get_current_user) in Use()
    """

    def role_checker(request: Request) -> dict[str, Any]:
        user = get_current_user(request)
        user_role = UserRole(user.get("role")) if user.get("role") else None
        if user_role not in roles:
            raise RpcError(
                -32003,
                "Permission denied",
                data={"code": "forbidden", "required_roles": [r.value for r in roles]},
            )
        return user

    return role_checker


def get_admin_user(request: Request) -> dict[str, Any]:
    """Require admin role and return user dict."""
    return require_role(UserRole.ADMIN)(request)


def get_optional_user(request: Request) -> dict[str, Any] | None:
    """Get current user if authenticated, otherwise return None."""
    try:
        return get_current_user(request)
    except RpcError:
        return None
