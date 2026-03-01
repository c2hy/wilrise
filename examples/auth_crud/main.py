#!/usr/bin/env -S uv run python
"""Auth + CRUD example: SQLAlchemy (SQLite), JWT, login and user CRUD over JSON-RPC.

This example demonstrates wilrise framework features:
- Dependency injection with Use()
- Pydantic validation for params
- RpcError for application errors
- Role-based access control
- Batch requests
- Notifications
- Router for method grouping
- Before/After hooks
- Custom exception mapping
"""
# pyright: reportCallIssue=false

from typing import Any

from sqlalchemy.orm import Session
from starlette.responses import Response
from wilrise import Router, Use, Wilrise
from wilrise.context import RpcContext
from wilrise.errors import RpcError

from . import database as _db
from .auth import (
    create_access_token,
    create_refresh_token,
    get_admin_user,
    get_current_user,
    hash_password,
    verify_password,
)
from .database import (
    create_audit_log,
    get_db_session,
    get_refresh_token,
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_audit_logs,
    revoke_all_user_tokens,
    revoke_refresh_token,
    update_last_login,
)
from .database import (
    create_refresh_token as db_create_refresh_token,
)
from .models import User, UserRole, UserStatus
from .schemas import (
    AuditLogListParams,
    AuditLogListResult,
    ChangePasswordParams,
    LoginParams,
    LoginResult,
    LogoutParams,
    PaginationMeta,
    RefreshTokenParams,
    SuccessResult,
    UserCreateParams,
    UserDeleteParams,
    UserGetParams,
    UserListParams,
    UserListResult,
    UserProfileUpdateParams,
    UserRoleUpdateParams,
    UserStatusUpdateParams,
    UserUpdateParams,
)

app = Wilrise(debug=True)

init_db()

auth_router = Router()
user_router = Router()
admin_router = Router()


@auth_router.method("login")
def login(
    params: LoginParams,
    db: Session = Use(get_db_session),
) -> dict[str, Any]:
    """Login with username and password; returns JWT access_token and refresh_token."""
    user = get_user_by_username(db, params.username)
    if not user or not verify_password(params.password, user.password_hash):
        raise RpcError(
            -32001, "Invalid username or password", data={"code": "auth_failed"}
        )
    if user.status != UserStatus.ACTIVE:
        raise RpcError(
            -32001, "Account is not active", data={"code": "account_inactive"}
        )
    access_token = create_access_token(user.username)
    refresh_token = create_refresh_token()
    db_create_refresh_token(db, user.id, refresh_token)
    update_last_login(db, user.id)
    create_audit_log(
        db,
        action="login",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
    )
    return LoginResult(
        access_token=access_token,
        refresh_token=refresh_token,
    ).model_dump()


@auth_router.method("refresh")
def refresh_token(
    params: RefreshTokenParams,
    db: Session = Use(get_db_session),
) -> dict[str, Any]:
    """Refresh access token using a valid refresh token."""
    rt = get_refresh_token(db, params.refresh_token)
    if not rt or rt.revoked:
        raise RpcError(
            -32001, "Invalid or revoked refresh token", data={"code": "invalid_token"}
        )
    from datetime import UTC, datetime

    if rt.expires_at.replace(tzinfo=None) < datetime.now(UTC).replace(tzinfo=None):
        raise RpcError(-32001, "Refresh token expired", data={"code": "token_expired"})
    user = get_user_by_id(db, rt.user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise RpcError(
            -32001, "User not found or inactive", data={"code": "user_inactive"}
        )
    access_token = create_access_token(user.username)
    new_refresh_token = create_refresh_token()
    rt.revoked = True
    db_create_refresh_token(db, user.id, new_refresh_token)
    db.commit()
    return LoginResult(
        access_token=access_token,
        refresh_token=new_refresh_token,
    ).model_dump()


@auth_router.method("logout")
def logout(
    params: LogoutParams,
    db: Session = Use(get_db_session),
    current_user: dict[str, Any] = Use(get_current_user),
) -> dict[str, Any]:
    """Logout and optionally revoke a refresh token."""
    if params.refresh_token:
        revoke_refresh_token(db, params.refresh_token)
    create_audit_log(
        db,
        action="logout",
        user_id=current_user.get("id"),
        resource_type="user",
        resource_id=current_user.get("id"),
    )
    return SuccessResult(message="Logged out successfully").model_dump()


@auth_router.method("me")
def auth_me(
    current_user: dict[str, Any] = Use(get_current_user),
) -> dict[str, Any]:
    """Return current user info (requires Authorization: Bearer <token>)."""
    return current_user


@user_router.method("create")
def user_create(
    params: UserCreateParams,
    db: Session = Use(get_db_session),
) -> dict[str, Any]:
    """Create a new user (public for demo; in production protect or use admin)."""
    if get_user_by_username(db, params.username):
        raise RpcError(
            -32002, "Username already exists", data={"username": params.username}
        )
    if params.email and get_user_by_username(db, params.email):
        raise RpcError(-32002, "Email already exists", data={"email": params.email})
    user = User(
        username=params.username,
        password_hash=hash_password(params.password),
        display_name=params.display_name or params.username,
        email=params.email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    create_audit_log(
        db,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        details={"username": user.username},
    )
    return user.to_dict()


@user_router.method("list")
def user_list(
    params: UserListParams = UserListParams(),
    db: Session = Use(get_db_session),
) -> dict[str, Any]:
    """List users with pagination and filters (public for demo)."""
    users, total = _db.list_users(
        db,
        skip=params.skip,
        limit=params.limit,
        status=params.status,
        role=params.role,
        search=params.search,
    )
    return UserListResult(
        users=[u.to_public_dict() for u in users],
        pagination=PaginationMeta(
            total=total,
            skip=params.skip,
            limit=params.limit,
            has_more=(params.skip + params.limit) < total,
        ),
    ).model_dump()


@user_router.method("get")
def user_get(
    params: UserGetParams,
    db: Session = Use(get_db_session),
    current_user: dict[str, Any] = Use(get_current_user),
) -> dict[str, Any] | None:
    """Get user by ID (requires auth)."""
    user = get_user_by_id(db, params.user_id)
    if not user:
        return None
    if current_user.get("role") == UserRole.ADMIN.value:
        return user.to_dict()
    return user.to_public_dict()


@user_router.method("update")
def user_update(
    params: UserUpdateParams,
    db: Session = Use(get_db_session),
    current_user: dict[str, Any] = Use(get_current_user),
) -> dict[str, Any] | None:
    """Update user by ID (requires auth; demo allows updating any user)."""
    user = get_user_by_id(db, params.user_id)
    if not user:
        return None
    if params.display_name is not None:
        user.display_name = params.display_name
    if params.password is not None:
        user.password_hash = hash_password(params.password)
    if params.email is not None:
        user.email = params.email
    if params.bio is not None:
        user.bio = params.bio
    db.commit()
    db.refresh(user)
    create_audit_log(
        db,
        action="user.update",
        user_id=current_user.get("id"),
        resource_type="user",
        resource_id=user.id,
    )
    return user.to_dict()


@user_router.method("delete")
def user_delete(
    params: UserDeleteParams,
    db: Session = Use(get_db_session),
    current_user: dict[str, Any] = Use(get_current_user),
) -> bool:
    """Delete user by ID (requires auth)."""
    user = get_user_by_id(db, params.user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    create_audit_log(
        db,
        action="user.delete",
        user_id=current_user.get("id"),
        resource_type="user",
        resource_id=params.user_id,
    )
    return True


@user_router.method("changePassword")
def user_change_password(
    params: ChangePasswordParams,
    db: Session = Use(get_db_session),
    current_user: dict[str, Any] = Use(get_current_user),
) -> dict[str, Any]:
    """Change own password."""
    user = get_user_by_id(db, current_user["id"])
    if not user or not verify_password(params.current_password, user.password_hash):
        raise RpcError(
            -32001, "Current password is incorrect", data={"code": "invalid_password"}
        )
    user.password_hash = hash_password(params.new_password)
    db.commit()
    revoke_all_user_tokens(db, user.id)
    create_audit_log(
        db,
        action="user.change_password",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
    )
    return SuccessResult(message="Password changed successfully").model_dump()


@user_router.method("updateProfile")
def user_update_profile(
    params: UserProfileUpdateParams,
    db: Session = Use(get_db_session),
    current_user: dict[str, Any] = Use(get_current_user),
) -> dict[str, Any]:
    """Update own profile."""
    user = get_user_by_id(db, current_user["id"])
    if not user:
        raise RpcError(-32001, "User not found", data={"code": "user_not_found"})
    if params.display_name is not None:
        user.display_name = params.display_name
    if params.email is not None:
        user.email = params.email
    if params.bio is not None:
        user.bio = params.bio
    db.commit()
    db.refresh(user)
    return user.to_dict()


@admin_router.method("user.setStatus")
def admin_set_user_status(
    params: UserStatusUpdateParams,
    db: Session = Use(get_db_session),
    _admin: dict[str, Any] = Use(get_admin_user),
) -> dict[str, Any] | None:
    """Update user status (admin only)."""
    user = get_user_by_id(db, params.user_id)
    if not user:
        return None
    user.status = params.status
    db.commit()
    db.refresh(user)
    create_audit_log(
        db,
        action="admin.set_status",
        user_id=_admin.get("id"),
        resource_type="user",
        resource_id=user.id,
        details={"new_status": params.status.value},
    )
    return user.to_dict()


@admin_router.method("user.setRole")
def admin_set_user_role(
    params: UserRoleUpdateParams,
    db: Session = Use(get_db_session),
    _admin: dict[str, Any] = Use(get_admin_user),
) -> dict[str, Any] | None:
    """Update user role (admin only)."""
    user = get_user_by_id(db, params.user_id)
    if not user:
        return None
    user.role = params.role
    db.commit()
    db.refresh(user)
    create_audit_log(
        db,
        action="admin.set_role",
        user_id=_admin.get("id"),
        resource_type="user",
        resource_id=user.id,
        details={"new_role": params.role.value},
    )
    return user.to_dict()


@admin_router.method("auditLogs")
def admin_list_audit_logs(
    params: AuditLogListParams,
    db: Session = Use(get_db_session),
    _admin: dict[str, Any] = Use(get_admin_user),
) -> dict[str, Any]:
    """List audit logs (admin only)."""
    logs, total = list_audit_logs(
        db,
        skip=params.skip,
        limit=params.limit,
        user_id=params.user_id,
        action=params.action,
    )
    return AuditLogListResult(
        logs=[log.to_dict() for log in logs],
        pagination=PaginationMeta(
            total=total,
            skip=params.skip,
            limit=params.limit,
            has_more=(params.skip + params.limit) < total,
        ),
    ).model_dump()


app.include_router(auth_router, prefix="auth.")
app.include_router(user_router, prefix="user.")
app.include_router(admin_router, prefix="admin.")


def log_request(
    context: RpcContext,
    duration_ms: float,
    response: Response | None,
    error: BaseException | None,
) -> None:
    """Request logger for demo."""
    if error:
        print(f"[AUDIT] {context.method} failed in {duration_ms:.2f}ms: {error}")


app.add_request_logger(log_request)


if __name__ == "__main__":
    print("Auth+CRUD JSON-RPC server: http://127.0.0.1:8000")
    print("\nMethods:")
    print("  auth.login, auth.refresh, auth.logout, auth.me")
    print("  user.create, user.list, user.get, user.update, user.delete")
    print("  user.changePassword, user.updateProfile")
    print("  admin.user.setStatus, admin.user.setRole, admin.auditLogs")
    print("\nUsage:")
    print("  1. Create user: user.create {username, password}")
    print("  2. Login: auth.login {username, password} -> access_token")
    print("  3. Use token: Authorization: Bearer <access_token>")
    app.run(host="127.0.0.1", port=8000)
