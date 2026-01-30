"""JWT creation/verification and get_current_user dependency."""

# pyright: reportUnknownMemberType=none

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from starlette.requests import Request
from wilrise.errors import RpcError

from .database import get_db_session, get_user_by_username
from .models import User

# JWT: use env in production
SECRET_KEY = os.environ.get("JWT_SECRET", "example-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


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


def create_access_token(sub: str) -> str:
    """Create JWT with subject (username)."""
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {"sub": sub, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate JWT; raise RpcError on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise RpcError(
            -32001, "Token expired", data={"code": "token_expired"}
        ) from None
    except jwt.InvalidTokenError:
        raise RpcError(
            -32001, "Invalid token", data={"code": "invalid_token"}
        ) from None


def get_current_user(request: Request) -> User:
    """Dependency: require valid JWT and return User. Raise RpcError if unauthorized."""
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
    session = get_db_session(request)
    user = get_user_by_username(session, str(sub))
    if not user:
        raise RpcError(-32001, "User not found", data={"code": "user_not_found"})
    return user
