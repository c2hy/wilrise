"""Pydantic schemas for auth_crud RPC params and responses."""

from pydantic import BaseModel, Field


class LoginParams(BaseModel):
    """Login request: username and password."""

    username: str = Field(..., min_length=1, max_length=64, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class LoginResult(BaseModel):
    """Login success: access_token and token_type."""

    access_token: str
    token_type: str = "bearer"


class UserCreateParams(BaseModel):
    """Create user: username, password, optional display_name."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=6)
    display_name: str = Field("", max_length=128)


class UserUpdateParams(BaseModel):
    """Update user: user_id and optional display_name and/or password."""

    user_id: int = Field(..., description="User ID to update")
    display_name: str | None = None
    password: str | None = Field(None, min_length=6)


class UserListParams(BaseModel):
    """List users: optional skip and limit."""

    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=100)
