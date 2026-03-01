"""Pydantic schemas for auth_crud RPC params and responses."""

from typing import Any

from pydantic import BaseModel, Field

from .models import UserRole, UserStatus


class LoginParams(BaseModel):
    """Login request: username and password."""

    username: str = Field(..., min_length=1, max_length=64, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class LoginResult(BaseModel):
    """Login success: access_token, refresh_token and token_type."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int = 86400


class RefreshTokenParams(BaseModel):
    """Refresh token request."""

    refresh_token: str = Field(..., description="Refresh token")


class LogoutParams(BaseModel):
    """Logout request (optional refresh_token to revoke)."""

    refresh_token: str | None = Field(None, description="Refresh token to revoke")


class UserCreateParams(BaseModel):
    """Create user: username, password, optional display_name, email."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=6)
    display_name: str = Field("", max_length=128)
    email: str | None = Field(None, description="User email")


class UserUpdateParams(BaseModel):
    """Update user: user_id and optional fields."""

    user_id: int = Field(..., description="User ID to update")
    display_name: str | None = Field(None, max_length=128)
    password: str | None = Field(None, min_length=6)
    email: str | None = None
    bio: str | None = Field(None, max_length=1000)


class UserStatusUpdateParams(BaseModel):
    """Update user status (admin only)."""

    user_id: int = Field(..., description="User ID to update")
    status: UserStatus = Field(..., description="New status")


class UserRoleUpdateParams(BaseModel):
    """Update user role (admin only)."""

    user_id: int = Field(..., description="User ID to update")
    role: UserRole = Field(..., description="New role")


class UserListParams(BaseModel):
    """List users: optional skip, limit, status filter, role filter, search."""

    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=100)
    status: UserStatus | None = Field(None, description="Filter by status")
    role: UserRole | None = Field(None, description="Filter by role")
    search: str | None = Field(
        None, max_length=64, description="Search in username/display_name"
    )


class UserGetParams(BaseModel):
    """Get user by ID."""

    user_id: int = Field(..., description="User ID")


class UserDeleteParams(BaseModel):
    """Delete user by ID."""

    user_id: int = Field(..., description="User ID to delete")


class ChangePasswordParams(BaseModel):
    """Change own password."""

    current_password: str = Field(..., min_length=1, description="Current password")
    new_password: str = Field(..., min_length=6, description="New password")


class UserProfileUpdateParams(BaseModel):
    """Update own profile."""

    display_name: str | None = Field(None, max_length=128)
    email: str | None = None
    bio: str | None = Field(None, max_length=1000)


class AuditLogListParams(BaseModel):
    """List audit logs (admin only)."""

    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=100)
    user_id: int | None = Field(None, description="Filter by user ID")
    action: str | None = Field(None, max_length=64, description="Filter by action")


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    total: int = Field(..., description="Total count")
    skip: int = Field(..., description="Current skip")
    limit: int = Field(..., description="Current limit")
    has_more: bool = Field(..., description="Has more results")


class UserListResult(BaseModel):
    """User list result with pagination."""

    users: list[dict[str, Any]]
    pagination: PaginationMeta


class AuditLogListResult(BaseModel):
    """Audit log list result with pagination."""

    logs: list[dict[str, Any]]
    pagination: PaginationMeta


class SuccessResult(BaseModel):
    """Generic success result."""

    success: bool = True
    message: str | None = None
