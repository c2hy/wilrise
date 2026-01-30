#!/usr/bin/env -S uv run python
"""Auth + CRUD example: SQLAlchemy (SQLite), JWT, login and user CRUD over JSON-RPC."""

# pyright: reportArgumentType=none, reportCallIssue=none

from typing import Annotated, Any

from sqlalchemy.orm import Session
from wilrise import Param, Use, Wilrise

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import (
    get_db_session,
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_users,
)
from .models import User
from .schemas import (
    LoginParams,
    LoginResult,
    UserCreateParams,
    UserListParams,
    UserUpdateParams,
)


# ---------- App ----------
# debug=True for demo only; use debug=False or from_env() in production (see README)
# Session lifecycle: get_db_session is a generator; framework closes it after each
# RPC request so session.close() runs in the generator's finally.
app = Wilrise(debug=True)

# Create tables on import (idempotent)
init_db()


# ---------- Public: login (no auth required) ----------
@app.method("auth.login")
def login(
    params: LoginParams,
    db: Session = Use(get_db_session),
) -> dict[str, Any]:
    """Login with username and password; returns JWT access_token."""
    user = get_user_by_username(db, params.username)
    if not user or not verify_password(params.password, user.password_hash):
        from wilrise.errors import RpcError

        raise RpcError(
            -32001, "Invalid username or password", data={"code": "auth_failed"}
        )
    token = create_access_token(user.username)
    return LoginResult(access_token=token).model_dump()


# ---------- Protected: current user ----------
@app.method("auth.me")
def auth_me(
    current_user: User = Use(get_current_user),
) -> dict[str, Any]:
    """Return current user info (requires Authorization: Bearer <token>)."""
    return current_user.to_dict()


# ---------- Protected: user CRUD ----------
@app.method("user.create")
def user_create(
    params: UserCreateParams,
    db: Session = Use(get_db_session),
) -> dict[str, Any]:
    """Create a new user (public for demo; in production protect or use admin)."""
    if get_user_by_username(db, params.username):
        from wilrise.errors import RpcError

        raise RpcError(
            -32002, "Username already exists", data={"username": params.username}
        )
    user = User(
        username=params.username,
        password_hash=hash_password(params.password),
        display_name=params.display_name or params.username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.to_dict()


@app.method("user.list")
def user_list(
    params: UserListParams = UserListParams(),
    db: Session = Use(get_db_session),
) -> list[dict[str, Any]]:
    """List users with pagination (public for demo)."""
    users = list_users(db, skip=params.skip, limit=params.limit)
    return [u.to_dict() for u in users]


@app.method("user.get")
def user_get(
    user_id: Annotated[int, Param(description="User ID")],
    db: Session = Use(get_db_session),
    current_user: User = Use(get_current_user),
) -> dict[str, Any] | None:
    """Get user by ID (requires auth)."""
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    return user.to_dict()


@app.method("user.update")
def user_update(
    params: UserUpdateParams,
    db: Session = Use(get_db_session),
    current_user: User = Use(get_current_user),
) -> dict[str, Any] | None:
    """Update user by ID (requires auth; demo allows updating any user)."""
    user = get_user_by_id(db, params.user_id)
    if not user:
        return None
    if params.display_name is not None:
        user.display_name = params.display_name
    if params.password is not None:
        user.password_hash = hash_password(params.password)
    db.commit()
    db.refresh(user)
    return user.to_dict()


@app.method("user.delete")
def user_delete(
    user_id: Annotated[int, Param(description="User ID to delete")],
    db: Session = Use(get_db_session),
    current_user: User = Use(get_current_user),
) -> bool:
    """Delete user by ID (requires auth)."""
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True


# ---------- Run ----------
if __name__ == "__main__":
    print("Auth+CRUD JSON-RPC server: http://127.0.0.1:8000")
    print(
        "Methods: auth.login, auth.me, user.create, user.list, user.get,"
        " user.update, user.delete"
    )
    print(
        "Login: pass LoginParams { username, password }; use returned"
        " access_token in header:"
    )
    print("  Authorization: Bearer <access_token>")
    app.run(host="127.0.0.1", port=8000)
