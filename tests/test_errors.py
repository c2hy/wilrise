"""Error handling tests — covers RpcError, ExceptionMapper, and Use exception paths.

FastAPI mapping:
  raise HTTPException(..)  → raise RpcError(code, message, data=)
  exception_handlers       → set_exception_mapper
  HTTPException(422)       → -32602 Invalid params
  HTTPException(404)       → RpcError(-32099, "Not found", ...)
"""
# pyright: reportUnusedFunction=false

from typing import Any

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient
from wilrise import RpcContext, RpcError, Use, Wilrise

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(app: Wilrise) -> TestClient:
    return TestClient(app.as_asgi())


def _rpc(
    method: str,
    params: dict[str, Any] | list[Any] | None = None,
    id: int = 1,
) -> dict[str, Any]:
    req: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        req["params"] = params
    return req


# ---------------------------------------------------------------------------
# RpcError  — FastAPI: raise HTTPException
# ---------------------------------------------------------------------------


class TestRpcError:
    def test_rpc_error_propagates_code_and_message(self) -> None:
        """raise RpcError(code, message) → error.code and error.message in response."""
        app = Wilrise()

        @app.method
        def login(token: str) -> str:
            if token != "valid":
                raise RpcError(-32001, "Authentication failed")
            return "ok"

        client = _client(app)
        r = client.post("/", json=_rpc("login", {"token": "bad"}))
        data = r.json()
        assert data["error"]["code"] == -32001
        assert data["error"]["message"] == "Authentication failed"

    def test_rpc_error_with_data(self) -> None:
        """RpcError(code, message, data=...) → error.data included in response."""
        app = Wilrise()

        @app.method
        def get_item(item_id: int) -> dict[str, Any]:
            raise RpcError(-32002, "Item not found", data={"item_id": item_id})

        client = _client(app)
        r = client.post("/", json=_rpc("get_item", {"item_id": 42}))
        data = r.json()
        assert data["error"]["code"] == -32002
        assert data["error"]["data"]["item_id"] == 42

    def test_rpc_error_in_async_method(self) -> None:
        """RpcError raised in async method is handled correctly."""
        app = Wilrise()

        @app.method
        async def async_fail() -> None:
            raise RpcError(-32003, "Async error")

        client = _client(app)
        r = client.post("/", json=_rpc("async_fail"))
        assert r.json()["error"]["code"] == -32003

    def test_rpc_error_code_out_of_range_raises_at_construction(self) -> None:
        """RpcError code outside -32099..-32000 → ValueError at construction time."""
        with pytest.raises(ValueError, match="-32099..-32000"):
            raise RpcError(-32100, "out of range")

    def test_rpc_error_code_boundary_valid(self) -> None:
        """RpcError code -32000 and -32099 are valid (boundary values)."""
        # Should not raise
        RpcError(-32000, "boundary low")
        RpcError(-32099, "boundary high")

    def test_rpc_error_id_echoed(self) -> None:
        """Error response echoes the request id."""
        app = Wilrise()

        @app.method
        def fail() -> None:
            raise RpcError(-32001, "fail")

        client = _client(app)
        r = client.post("/", json=_rpc("fail", id=77))
        assert r.json()["id"] == 77

    def test_rpc_error_notification_no_response(self) -> None:
        """RpcError in notification → no response (204)."""
        app = Wilrise()

        @app.method
        def fail() -> None:
            raise RpcError(-32001, "fail")

        client = _client(app)
        r = client.post("/", json={"jsonrpc": "2.0", "method": "fail"})
        assert r.status_code == 204


# ---------------------------------------------------------------------------
# Use() provider exceptions
# ---------------------------------------------------------------------------


class TestUseProviderExceptions:
    def test_use_provider_raises_returns_32603(self) -> None:
        """When a Use provider raises a plain exception → -32603 Internal error."""
        app = Wilrise()

        def bad_provider(request: Request) -> str:
            raise ConnectionError("DB is down")

        @app.method
        def get_data(db: str = Use(bad_provider)) -> str:
            return db

        client = _client(app)
        r = client.post("/", json=_rpc("get_data"))
        assert r.json()["error"]["code"] == -32603

    def test_use_provider_raises_rpc_error(self) -> None:
        """When a Use provider raises RpcError → that error is returned."""
        app = Wilrise()

        def auth_provider(request: Request) -> str:
            raise RpcError(-32001, "Unauthorized")

        @app.method
        def secret(token: str = Use(auth_provider)) -> str:
            return token

        client = _client(app)
        r = client.post("/", json=_rpc("secret"))
        assert r.json()["error"]["code"] == -32001


# ---------------------------------------------------------------------------
# ExceptionMapper  — FastAPI: exception_handlers / middleware for mapping
# ---------------------------------------------------------------------------


class TestExceptionMapper:
    def test_exception_mapper_maps_known_exception(self) -> None:
        """set_exception_mapper maps a known exception class to an RPC error code."""

        class DbError(Exception):
            pass

        class MyMapper:
            def map_exception(
                self, exc: Exception, context: RpcContext
            ) -> tuple[int, str, object] | None:
                if isinstance(exc, DbError):
                    return -32010, "Database error", {"detail": str(exc)}
                return None

        app = Wilrise()
        app.set_exception_mapper(MyMapper())

        @app.method
        def fetch() -> None:
            raise DbError("connection timeout")

        client = _client(app)
        r = client.post("/", json=_rpc("fetch"))
        data = r.json()
        assert data["error"]["code"] == -32010
        assert data["error"]["message"] == "Database error"
        assert data["error"]["data"]["detail"] == "connection timeout"

    def test_exception_mapper_returns_none_falls_back_to_32603(self) -> None:
        """When mapper returns None for an exception → default -32603."""

        class MyMapper:
            def map_exception(
                self, exc: Exception, context: RpcContext
            ) -> tuple[int, str, object] | None:
                return None  # always fall back

        app = Wilrise()
        app.set_exception_mapper(MyMapper())

        @app.method
        def boom() -> None:
            raise ValueError("unexpected")

        client = _client(app)
        r = client.post("/", json=_rpc("boom"))
        assert r.json()["error"]["code"] == -32603

    def test_exception_mapper_receives_rpc_context(self) -> None:
        """ExceptionMapper receives the RpcContext so it can inspect method/id."""

        received: list[RpcContext] = []

        class CtxMapper:
            def map_exception(
                self, exc: Exception, context: RpcContext
            ) -> tuple[int, str, object] | None:
                received.append(context)
                return None

        app = Wilrise()
        app.set_exception_mapper(CtxMapper())

        @app.method
        def fail() -> None:
            raise RuntimeError("oops")

        client = _client(app)
        client.post("/", json=_rpc("fail", id=55))
        assert received[0].method == "fail"
        assert received[0].request_id == 55

    def test_set_exception_mapper_none_resets_to_default(self) -> None:
        """set_exception_mapper(None) restores the default -32603 behavior."""

        class MyMapper:
            def map_exception(
                self, exc: Exception, context: RpcContext
            ) -> tuple[int, str, object] | None:
                return -32010, "mapped", None

        app = Wilrise()
        app.set_exception_mapper(MyMapper())
        app.set_exception_mapper(None)  # reset

        @app.method
        def fail() -> None:
            raise RuntimeError("oops")

        client = _client(app)
        r = client.post("/", json=_rpc("fail"))
        assert r.json()["error"]["code"] == -32603
