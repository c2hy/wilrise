"""Core dispatch tests comparable to FastAPI routing.

FastAPI mapping:
  @app.get("/path")   → @app.method / @app.method("name")
  sync endpoint       → runs in thread pool (same as FastAPI def endpoints)
  async endpoint      → runs directly in the event loop
  404 Not Found       → -32601 Method not found
  405 Method Not Allowed → 405 response for non-POST
  422 Unprocessable   → -32602 Invalid params / missing required arg
  500 Internal server → -32603 Internal error
  debug mode          → expose exception text in error.message
"""
# pyright: reportUnusedFunction=false

import asyncio
from typing import Any

from starlette.testclient import TestClient
from wilrise import Wilrise

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(app: Wilrise, path: str = "/") -> TestClient:
    return TestClient(app.as_asgi(path=path))


def _rpc(
    method: str,
    params: dict[str, Any] | list[Any] | None = None,
    id: int | str | None = 1,
) -> dict[str, Any]:
    req: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        req["params"] = params
    if id is not None:
        req["id"] = id
    return req


# ---------------------------------------------------------------------------
# Method registration
# ---------------------------------------------------------------------------


class TestMethodRegistration:
    def test_method_decorator_no_arg_uses_function_name(self) -> None:
        """@app.method with no args → RPC name == function name."""
        app = Wilrise()

        @app.method
        def echo(value: str) -> str:
            return value

        client = _client(app)
        r = client.post("/", json=_rpc("echo", {"value": "hi"}))
        assert r.status_code == 200
        assert r.json()["result"] == "hi"

    def test_method_decorator_with_custom_name(self) -> None:
        """@app.method("custom.name") → registered under the given name."""
        app = Wilrise()

        @app.method("user.getById")
        def get_user_by_id(user_id: int) -> dict[str, Any]:
            return {"id": user_id}

        client = _client(app)
        r = client.post("/", json=_rpc("user.getById", {"user_id": 42}))
        assert r.status_code == 200
        assert r.json()["result"]["id"] == 42

    def test_method_with_no_params(self) -> None:
        """Method with no parameters can be called with omitted params."""
        app = Wilrise()

        @app.method
        def ping() -> str:
            return "pong"

        client = _client(app)
        r = client.post("/", json=_rpc("ping"))
        assert r.status_code == 200
        assert r.json()["result"] == "pong"

    def test_method_returns_none(self) -> None:
        """A method that returns None produces result: null."""
        app = Wilrise()

        @app.method
        def noop() -> None:
            return None

        client = _client(app)
        r = client.post("/", json=_rpc("noop"))
        data = r.json()
        assert r.status_code == 200
        assert "error" not in data
        assert data["result"] is None

    def test_method_returns_list(self) -> None:
        app = Wilrise()

        @app.method
        def items() -> list[int]:
            return [1, 2, 3]

        client = _client(app)
        r = client.post("/", json=_rpc("items"))
        assert r.json()["result"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Sync vs async methods
# ---------------------------------------------------------------------------


class TestSyncAsync:
    def test_sync_method_runs_without_blocking(self) -> None:
        """Sync def methods are dispatched via asyncio.to_thread (same as FastAPI)."""
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = _client(app)
        r = client.post("/", json=_rpc("add", {"a": 10, "b": 20}))
        assert r.json()["result"] == 30

    def test_async_method(self) -> None:
        """async def methods run directly in the event loop."""
        app = Wilrise()

        @app.method
        async def async_add(a: int, b: int) -> int:
            await asyncio.sleep(0)
            return a + b

        client = _client(app)
        r = client.post("/", json=_rpc("async_add", {"a": 5, "b": 7}))
        assert r.json()["result"] == 12


# ---------------------------------------------------------------------------
# Response ID echo
# ---------------------------------------------------------------------------


class TestResponseId:
    def test_id_is_echoed(self) -> None:
        app = Wilrise()

        @app.method
        def greet() -> str:
            return "hello"

        client = _client(app)
        for req_id in [1, "abc", 99]:
            r = client.post("/", json=_rpc("greet", id=req_id))
            assert r.json()["id"] == req_id

    def test_id_null_is_echoed(self) -> None:
        """id: null ← valid per JSON-RPC 2.0."""
        app = Wilrise()

        @app.method
        def greet() -> str:
            return "hello"

        client = _client(app)
        req = {"jsonrpc": "2.0", "method": "greet", "id": None}
        r = client.post("/", json=req)
        assert r.json()["id"] is None


# ---------------------------------------------------------------------------
# Error codes — FastAPI analogy: 404/405/422/500
# ---------------------------------------------------------------------------


class TestErrorCodes:
    def test_method_not_found_returns_32601(self) -> None:
        """Unknown method → -32601 (FastAPI: 404)."""
        app = Wilrise()
        client = _client(app)
        r = client.post("/", json=_rpc("no_such_method"))
        data = r.json()
        assert r.status_code == 200
        assert data["error"]["code"] == -32601

    def test_non_post_returns_405(self) -> None:
        """GET/PUT/etc → 405 (FastAPI: 405 Method Not Allowed)."""
        app = Wilrise()
        client = _client(app)
        r = client.get("/")
        assert r.status_code == 405

    def test_invalid_json_returns_32700(self) -> None:
        """Malformed JSON → -32700 Parse error (FastAPI: 400)."""
        app = Wilrise()
        client = _client(app)
        r = client.post(
            "/",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == -32700

    def test_missing_jsonrpc_field_returns_32600(self) -> None:
        """Body missing jsonrpc:"2.0" → -32600 Invalid Request."""
        app = Wilrise()
        client = _client(app)
        r = client.post("/", json={"method": "add", "id": 1})
        assert r.json()["error"]["code"] == -32600

    def test_missing_method_field_returns_32600(self) -> None:
        """Body missing method field → -32600."""
        app = Wilrise()
        client = _client(app)
        r = client.post("/", json={"jsonrpc": "2.0", "id": 1})
        assert r.json()["error"]["code"] == -32600

    def test_reserved_rpc_prefix_returns_32600(self) -> None:
        """Method starting with 'rpc.' is reserved → -32600."""
        app = Wilrise()
        client = _client(app)
        r = client.post("/", json=_rpc("rpc.discover"))
        assert r.json()["error"]["code"] == -32600

    def test_params_not_object_or_array_returns_32600(self) -> None:
        """params is a scalar (not dict/list) → -32600."""
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = _client(app)
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "add", "params": 42, "id": 1},
        )
        assert r.json()["error"]["code"] == -32600

    def test_missing_required_param_returns_32602(self) -> None:
        """Missing required parameter → -32602 (FastAPI: 422)."""
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = _client(app)
        r = client.post("/", json=_rpc("add", {"a": 1}))
        data = r.json()
        assert data["error"]["code"] == -32602

    def test_method_exception_returns_32603(self) -> None:
        """Unhandled exception in method → -32603 (FastAPI: 500)."""
        app = Wilrise()

        @app.method
        def boom() -> None:
            raise RuntimeError("unexpected")

        client = _client(app)
        r = client.post("/", json=_rpc("boom"))
        assert r.json()["error"]["code"] == -32603

    def test_non_serializable_result_returns_32603(self) -> None:
        """Method returning a non-JSON-serializable value → -32603."""
        app = Wilrise()

        @app.method
        def bad_result() -> object:
            return object()  # not serializable

        client = _client(app)
        r = client.post("/", json=_rpc("bad_result"))
        assert r.json()["error"]["code"] == -32603


# ---------------------------------------------------------------------------
# Debug mode
# ---------------------------------------------------------------------------


class TestDebugMode:
    def test_debug_true_exposes_exception_message(self) -> None:
        """debug=True: error.message contains the actual exception text."""
        app = Wilrise(debug=True)

        @app.method
        def fail() -> None:
            raise ValueError("secret error detail")

        client = _client(app)
        r = client.post("/", json=_rpc("fail"))
        data = r.json()
        assert data["error"]["code"] == -32603
        assert "secret error detail" in data["error"]["message"]

    def test_debug_false_hides_exception_message(self) -> None:
        """debug=False (default): error.message is generic, no leakage."""
        app = Wilrise(debug=False)

        @app.method
        def fail() -> None:
            raise ValueError("secret error detail")

        client = _client(app)
        r = client.post("/", json=_rpc("fail"))
        data = r.json()
        assert data["error"]["code"] == -32603
        assert "secret error detail" not in data["error"]["message"]


# ---------------------------------------------------------------------------
# Batch requests (JSON-RPC batch)
# ---------------------------------------------------------------------------


class TestBatch:
    def test_batch_returns_results_in_order(self) -> None:
        """Batch of requests returns responses in the same order."""
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = _client(app)
        r = client.post(
            "/",
            json=[
                _rpc("add", {"a": 1, "b": 2}),
                _rpc("add", {"a": 10, "b": 20}, id=2),
            ],
        )
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 2
        assert results[0]["result"] == 3
        assert results[1]["result"] == 30

    def test_batch_mixed_success_and_error(self) -> None:
        """One bad method in batch does not fail the whole batch."""
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = _client(app)
        r = client.post(
            "/",
            json=[
                _rpc("add", {"a": 1, "b": 2}),
                _rpc("no_such_method", id=2),
            ],
        )
        results = r.json()
        assert any("result" in x for x in results)
        assert any("error" in x and x["error"]["code"] == -32601 for x in results)

    def test_batch_all_notifications_returns_204(self) -> None:
        """Batch where all are notifications → 204 No Content."""
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = _client(app)
        # Notifications have no "id" key
        r = client.post(
            "/",
            json=[
                {"jsonrpc": "2.0", "method": "add", "params": {"a": 1, "b": 2}},
                {"jsonrpc": "2.0", "method": "add", "params": {"a": 3, "b": 4}},
            ],
        )
        assert r.status_code == 204

    def test_empty_batch_returns_32600(self) -> None:
        """Empty batch array → -32600."""
        app = Wilrise()
        client = _client(app)
        r = client.post("/", json=[])
        assert r.status_code == 400
        assert r.json()["error"]["code"] == -32600

    def test_batch_exceeds_max_batch_size(self) -> None:
        """Batch exceeding max_batch_size → -32600."""
        app = Wilrise(max_batch_size=2)

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = _client(app)
        batch = [_rpc("add", {"a": 1, "b": 1}, id=i) for i in range(3)]
        r = client.post("/", json=batch)
        assert r.status_code == 400
        assert r.json()["error"]["code"] == -32600


# ---------------------------------------------------------------------------
# Notification (no "id" → no response body)
# ---------------------------------------------------------------------------


class TestNotification:
    def test_notification_returns_204(self) -> None:
        """Single notification (no id) → 204 No Content, no body."""
        app = Wilrise()
        called = []

        @app.method
        def notify(msg: str) -> None:
            called.append(msg)

        client = _client(app)
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "notify", "params": {"msg": "hello"}},
        )
        assert r.status_code == 204
        assert called == ["hello"]

    def test_notification_unknown_method_still_204(self) -> None:
        """Notification for unknown method → still 204 (no error response)."""
        app = Wilrise()
        client = _client(app)
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "no_such_method"},
        )
        assert r.status_code == 204


# ---------------------------------------------------------------------------
# Positional (array) params
# ---------------------------------------------------------------------------


class TestArrayParams:
    def test_array_params_bound_by_position(self) -> None:
        """params: [a, b] → bound to first, second parameter by position."""
        app = Wilrise()

        @app.method
        def subtract(x: int, y: int) -> int:
            return x - y

        client = _client(app)
        r = client.post("/", json=_rpc("subtract", [10, 3]))
        assert r.json()["result"] == 7

    def test_array_params_single_element(self) -> None:
        app = Wilrise()

        @app.method
        def double(n: int) -> int:
            return n * 2

        client = _client(app)
        r = client.post("/", json=_rpc("double", [5]))
        assert r.json()["result"] == 10


# ---------------------------------------------------------------------------
# Request size limit
# ---------------------------------------------------------------------------


class TestRequestSizeLimit:
    def test_request_exceeds_content_length(self) -> None:
        """Content-Length header > max_request_size → 413."""
        app = Wilrise(max_request_size=10)

        client = _client(app)
        body = b'{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}'
        r = client.post(
            "/",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        assert r.status_code == 413


# ---------------------------------------------------------------------------
# Custom ASGI path
# ---------------------------------------------------------------------------


class TestCustomPath:
    def test_custom_path(self) -> None:
        """as_asgi(path='/rpc') → method dispatched at /rpc."""
        app = Wilrise()

        @app.method
        def ping() -> str:
            return "pong"

        client = _client(app, path="/rpc")
        r = client.post("/rpc", json=_rpc("ping"))
        assert r.json()["result"] == "pong"
