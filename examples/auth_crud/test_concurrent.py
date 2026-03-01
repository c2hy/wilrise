#!/usr/bin/env -S uv run python
"""Concurrency tests for auth_crud: no transaction/session leakage under parallel."""

# Set test DB before any auth_crud import so engine uses it
import os
import tempfile

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ.setdefault("AUTH_CRUD_DB", _db_path)

import asyncio
from typing import Any

import httpx

# Import after env is set
from auth_crud.main import app

ASGI_APP = app.as_asgi()
BASE = "http://test"
CONCURRENCY = 20  # number of parallel users/requests


def rpc_request(
    method: str, params: dict[str, Any] | None = None, token: str | None = None
) -> dict[str, Any]:
    """Build JSON-RPC request body."""
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params is not None:
        body["params"] = params
    return body


async def post(
    client: httpx.AsyncClient,
    body: dict[str, Any],
    token: str | None = None,
) -> dict[str, Any]:
    """POST JSON-RPC and return parsed JSON."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = await client.post(BASE, json=body, headers=headers)
    r.raise_for_status()
    return r.json()


async def create_user(client: httpx.AsyncClient, i: int) -> dict[str, Any]:
    """Create user user_{i}; return response JSON. Keyed params when Pydantic+Use."""
    body = rpc_request(
        "user.create",
        {
            "params": {
                "username": f"user_{i}",
                "password": "pass123",
                "display_name": f"User {i}",
            }
        },
    )
    return await post(client, body)


async def login(client: httpx.AsyncClient, i: int) -> str:
    """Login as user_{i}; return access_token. Keyed params when Pydantic+Use."""
    body = rpc_request(
        "auth.login",
        {"params": {"username": f"user_{i}", "password": "pass123"}},
    )
    data = await post(client, body)
    token = data.get("result", {}).get("access_token")
    if not token:
        raise AssertionError(f"login failed for user_{i}: {data}")
    return token


async def user_list(client: httpx.AsyncClient) -> list[Any]:
    """Call user.list and return result.users. Keyed params (params + Use)."""
    body = rpc_request("user.list", {"params": {"skip": 0, "limit": 100}})
    data = await post(client, body)
    if "error" in data:
        raise AssertionError(f"user.list error: {data}")
    result = data.get("result", {})
    return result.get("users", []) if isinstance(result, dict) else result


async def user_get(
    client: httpx.AsyncClient, user_id: int, token: str
) -> dict[str, Any] | None:
    """Get user by id (with auth)."""
    body = rpc_request("user.get", {"user_id": user_id})
    data = await post(client, body, token=token)
    if "error" in data:
        raise AssertionError(f"user.get error: {data}")
    return data.get("result")


async def user_update(
    client: httpx.AsyncClient,
    user_id: int,
    display_name: str,
    token: str,
) -> dict[str, Any]:
    """Update user display_name (with auth). Keyed params (params + Use)."""
    body = rpc_request(
        "user.update",
        {"params": {"user_id": user_id, "display_name": display_name}},
    )
    data = await post(client, body, token=token)
    if "error" in data:
        raise AssertionError(f"user.update error: {data}")
    return data.get("result", {})


async def user_delete(client: httpx.AsyncClient, user_id: int, token: str) -> bool:
    """Delete user (with auth)."""
    body = rpc_request("user.delete", {"user_id": user_id})
    data = await post(client, body, token=token)
    if "error" in data:
        raise AssertionError(f"user.delete error: {data}")
    return data.get("result") is True


async def run_concurrent_creates(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Create CONCURRENCY users in parallel; assert all succeed and no duplicates."""
    tasks = [create_user(client, i) for i in range(CONCURRENCY)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[dict[str, Any]] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            raise AssertionError(f"create user_{i} failed: {r}") from r
        assert isinstance(r, dict), "expected dict response"
        if "error" in r:
            raise AssertionError(f"create user_{i} RPC error: {r}")
        out.append(r["result"])
    # All usernames must be unique
    usernames = [u["username"] for u in out]
    assert len(usernames) == len(set(usernames)), "duplicate usernames"
    return out


async def run_concurrent_logins(client: httpx.AsyncClient) -> list[str]:
    """Login as each user in parallel; return list of tokens."""
    tasks = [login(client, i) for i in range(CONCURRENCY)]
    return await asyncio.gather(*tasks)


async def run_concurrent_lists(client: httpx.AsyncClient, expected_count: int) -> None:
    """Call user.list many times in parallel; assert count is stable."""

    async def one_list() -> int:
        users = await user_list(client)
        return len(users)

    tasks = [one_list() for _ in range(CONCURRENCY)]
    counts = await asyncio.gather(*tasks)
    for c in counts:
        assert c == expected_count, f"expected {expected_count} users, got {c}"


async def run_concurrent_gets(
    client: httpx.AsyncClient,
    user_ids: list[int],
    tokens: list[str],
) -> list[dict[str, Any]]:
    """Get each user by id in parallel (own token); assert no cross-request data."""
    tasks = [
        user_get(client, uid, token)
        for uid, token in zip(user_ids, tokens, strict=True)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[dict[str, Any]] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            raise AssertionError(f"get user_{i} failed: {r}") from r
        if r is None:
            raise AssertionError(f"get user_{i} returned None")
        assert isinstance(r, dict), "expected dict response"
        out.append(r)
    return out


async def run_concurrent_updates(
    client: httpx.AsyncClient,
    user_ids: list[int],
    tokens: list[str],
) -> None:
    """Update each user's display_name in parallel."""
    tasks = [
        user_update(client, uid, f"Updated {uid}", token)
        for uid, token in zip(user_ids, tokens, strict=True)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            raise AssertionError(f"update user_{i} failed: {r}") from r


async def run_concurrent_deletes(
    client: httpx.AsyncClient,
    user_ids: list[int],
    tokens: list[str],
) -> None:
    """Delete each user in parallel."""
    tasks = [
        user_delete(client, uid, token)
        for uid, token in zip(user_ids, tokens, strict=True)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            raise AssertionError(f"delete user_{i} failed: {r}") from r
        assert r is True, f"delete user_{i} returned {r}"


async def main() -> None:
    transport = httpx.ASGITransport(app=ASGI_APP)
    async with httpx.AsyncClient(
        transport=transport, base_url=BASE, timeout=30.0
    ) as client:
        print("1. Concurrent create: create", CONCURRENCY, "users in parallel")
        created: list[dict[str, Any]] = await run_concurrent_creates(client)
        user_ids: list[int] = [u["id"] for u in created]
        assert len(user_ids) == CONCURRENCY

        print("2. Concurrent login: login as each user in parallel")
        tokens = await run_concurrent_logins(client)
        assert len(tokens) == CONCURRENCY

        print("3. Concurrent list: call user.list", CONCURRENCY, "times in parallel")
        await run_concurrent_lists(client, expected_count=CONCURRENCY)

        print("4. Concurrent get: get each user by id (own token)")
        got = await run_concurrent_gets(client, user_ids, tokens)
        for i, u in enumerate(got):
            assert u["id"] == user_ids[i], f"user id mismatch at {i}"
            assert u["username"] == f"user_{i}"

        print("5. Concurrent update: update each user display_name")
        await run_concurrent_updates(client, user_ids, tokens)

        print("6. Concurrent get again: verify updates")
        got2 = await run_concurrent_gets(client, user_ids, tokens)
        for i, u in enumerate(got2):
            assert u["display_name"] == f"Updated {user_ids[i]}", (
                f"update not visible at {i}"
            )

        print("7. Concurrent delete: delete all users in parallel")
        await run_concurrent_deletes(client, user_ids, tokens)

        print("8. user.list must be empty")
        users = await user_list(client)
        assert len(users) == 0, f"expected 0 users, got {len(users)}"

    print("All concurrency checks passed (no transaction/session leakage).")


async def test_concurrent_crud() -> None:
    """Pytest entry point: 20 concurrent users, no session/transaction leakage.

    Exercises wilrise's async dispatch, generator-based Use() cleanup,
    and SQLAlchemy session isolation under parallel load — all in one test.
    """
    await main()


if __name__ == "__main__":
    asyncio.run(main())
