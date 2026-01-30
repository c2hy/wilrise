"""Integration tests for auth_crud: login, user CRUD over JSON-RPC."""

import os
import tempfile
from typing import Any, cast

from starlette.testclient import TestClient

# Set test DB before importing app
_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ.setdefault("AUTH_CRUD_DB", _db_path)

from auth_crud.main import app  # noqa: E402

client = TestClient(app.as_asgi())


def test_login_invalid_returns_error() -> None:
    """Invalid login returns RPC error."""
    r = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "auth.login",
            "params": {"params": {"username": "nobody", "password": "x"}},
            "id": 1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32001


def test_create_user_and_list() -> None:
    """Create user via user.create, then user.list includes it."""
    r = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "user.create",
            "params": {
                "params": {
                    "username": "testuser",
                    "password": "secret123",
                    "display_name": "Test User",
                }
            },
            "id": 1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    user = data["result"]
    assert user["username"] == "testuser"

    r2 = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "user.list",
            "params": {"params": {"skip": 0, "limit": 10}},
            "id": 2,
        },
    )
    assert r2.status_code == 200
    result = r2.json()["result"]
    assert isinstance(result, list)
    result_list = cast(list[dict[str, Any]], result)
    usernames: list[str] = [u["username"] for u in result_list]
    assert "testuser" in usernames


def test_login_then_me() -> None:
    """Login returns token; auth.me with token returns user."""
    # Create user first (test is self-contained)
    client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "user.create",
            "params": {
                "params": {
                    "username": "meuser",
                    "password": "pass456",
                    "display_name": "Me",
                }
            },
            "id": 0,
        },
    )
    r = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "auth.login",
            "params": {"params": {"username": "meuser", "password": "pass456"}},
            "id": 1,
        },
    )
    assert r.status_code == 200
    token = r.json()["result"]["access_token"]
    assert token

    r2 = client.post(
        "/",
        json={"jsonrpc": "2.0", "method": "auth.me", "params": {}, "id": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    me = r2.json()["result"]
    assert me["username"] == "meuser"
