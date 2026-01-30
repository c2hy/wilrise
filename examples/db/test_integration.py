"""Integration tests for examples/db: real SQLite + JSON-RPC."""

import os
import tempfile
from typing import Any, cast

from starlette.testclient import TestClient

# Use temp DB before importing app so engine uses it
_fd, _path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ.setdefault("DB_EXAMPLE_PATH", _path)

from db.main import app  # noqa: E402

client = TestClient(app.as_asgi())


def test_create_user_and_get() -> None:
    """Create user via RPC, then get_user returns same data."""
    r = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "create_user",
            "params": {"name": "Alice", "email": "alice@example.com"},
            "id": 1,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    user = data["result"]
    assert user["name"] == "Alice"
    assert user["email"] == "alice@example.com"
    user_id = user["id"]

    r2 = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "get_user",
            "params": {"user_id": user_id},
            "id": 2,
        },
    )
    assert r2.status_code == 200
    got = r2.json()["result"]
    assert got["id"] == user_id
    assert got["name"] == "Alice"
    assert got["email"] == "alice@example.com"


def test_list_users() -> None:
    """list_users returns all created users."""
    r = client.post(
        "/",
        json={"jsonrpc": "2.0", "method": "list_users", "params": {}, "id": 1},
    )
    assert r.status_code == 200
    result = r.json()["result"]
    assert isinstance(result, list)
    result_list = cast(list[dict[str, Any]], result)
    assert len(result_list) >= 1
    names: list[str] = [u["name"] for u in result_list]
    assert "Alice" in names


def test_get_user_not_found() -> None:
    """get_user with non-existent id returns null."""
    r = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "get_user",
            "params": {"user_id": 99999},
            "id": 1,
        },
    )
    assert r.status_code == 200
    assert r.json()["result"] is None
