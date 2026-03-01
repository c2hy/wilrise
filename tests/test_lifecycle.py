"""Lifecycle and extension point tests — startup/shutdown, middleware, hooks, context.

FastAPI mapping:
  @app.on_event("startup")   → app.add_startup(fn)
  @app.on_event("shutdown")  → app.add_shutdown(fn)
  add_middleware(...)        → app.add_middleware(cls, **kwargs)
  middleware / dependencies  → add_before_call_hook / add_after_call_hook
  request.state              → request.state.rpc_context / RpcContext
  X-Request-ID header        → RpcContext.http_request_id
"""

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.testclient import TestClient
from wilrise import RpcContext, Use, Wilrise, get_rpc_context

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
# Startup / Shutdown (FastAPI: @app.on_event / lifespan)
# ---------------------------------------------------------------------------


class TestStartupShutdown:
    def test_sync_startup_called_on_start(self) -> None:
        startup_log: list[str] = []
        app = Wilrise()

        def on_start() -> None:
            startup_log.append("started")

        app.add_startup(on_start)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        with TestClient(app.as_asgi()) as client:
            client.post("/", json=_rpc("ping"))

        assert "started" in startup_log

    def test_async_startup_called_on_start(self) -> None:
        startup_log: list[str] = []
        app = Wilrise()

        async def on_start() -> None:
            startup_log.append("async_started")

        app.add_startup(on_start)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        with TestClient(app.as_asgi()) as client:
            client.post("/", json=_rpc("ping"))

        assert "async_started" in startup_log

    def test_shutdown_called_on_exit(self) -> None:
        shutdown_log: list[str] = []
        app = Wilrise()

        def on_stop() -> None:
            shutdown_log.append("stopped")

        app.add_shutdown(on_stop)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        with TestClient(app.as_asgi()) as client:
            client.post("/", json=_rpc("ping"))

        assert "stopped" in shutdown_log

    def test_multiple_shutdowns_run_in_reverse_order(self) -> None:
        """Multiple shutdown hooks run in reverse registration order (LIFO)."""
        order: list[int] = []
        app = Wilrise()
        app.add_shutdown(lambda: order.append(1))
        app.add_shutdown(lambda: order.append(2))

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        with TestClient(app.as_asgi()) as client:
            client.post("/", json=_rpc("ping"))

        assert order == [2, 1]


# ---------------------------------------------------------------------------
# Middleware (FastAPI: add_middleware)
# ---------------------------------------------------------------------------


class TestMiddleware:
    def test_middleware_runs_around_request(self) -> None:
        """Starlette middleware registered via add_middleware wraps each request."""
        order: list[str] = []

        class TraceMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):  # type: ignore[override]
                order.append("before")
                response = await call_next(request)
                order.append("after")
                return response

        app = Wilrise()
        app.add_middleware(TraceMiddleware)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        client = _client(app)
        client.post("/", json=_rpc("ping"))
        assert order == ["before", "after"]

    def test_middleware_can_add_headers(self) -> None:
        """Middleware can mutate the response (e.g. inject a header)."""

        class HeaderMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):  # type: ignore[override]
                response = await call_next(request)
                response.headers["X-Custom"] = "wilrise"
                return response

        app = Wilrise()
        app.add_middleware(HeaderMiddleware)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        client = _client(app)
        r = client.post("/", json=_rpc("ping"))
        assert r.headers.get("X-Custom") == "wilrise"


# ---------------------------------------------------------------------------
# Before-call hooks (FastAPI: Depends / middleware for auth guards)
# ---------------------------------------------------------------------------


class TestBeforeCallHook:
    def test_hook_returns_none_allows_call(self) -> None:
        """Hook returning None → method is called normally."""
        app = Wilrise()
        app.add_before_call_hook(lambda name, params, req: None)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        client = _client(app)
        r = client.post("/", json=_rpc("ping"))
        assert r.json()["result"] == "pong"

    def test_hook_returns_error_dict_aborts_call(self) -> None:
        """Hook returning an error dict → method is NOT called; error is returned."""

        app = Wilrise()
        error_resp = {
            "jsonrpc": "2.0",
            "error": {"code": -32001, "message": "Blocked"},
            "id": 1,
        }
        app.add_before_call_hook(lambda name, params, req: error_resp)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        client = _client(app)
        r = client.post("/", json=_rpc("ping"))
        data = r.json()
        assert data["error"]["code"] == -32001

    def test_async_hook_is_awaited(self) -> None:
        """Async before-call hook is properly awaited."""
        app = Wilrise()

        async def async_hook(name: str, params, request: Request):
            return None

        app.add_before_call_hook(async_hook)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        client = _client(app)
        r = client.post("/", json=_rpc("ping"))
        assert r.json()["result"] == "pong"

    def test_hook_receives_method_name_and_params(self) -> None:
        """Hook receives correct method_name and params."""
        received: list[tuple[str, Any]] = []

        def capturing_hook(name: str, params, request: Request):
            received.append((name, params))
            return None

        app = Wilrise()
        app.add_before_call_hook(capturing_hook)

        @app.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        client = _client(app)
        client.post("/", json=_rpc("add", {"a": 1, "b": 2}))
        assert received[0][0] == "add"
        assert received[0][1] == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# After-call hooks (FastAPI: BackgroundTasks or response middleware)
# ---------------------------------------------------------------------------


class TestAfterCallHook:
    def test_hook_called_after_successful_method(self) -> None:
        """After-call hook executes after successful method execution."""
        seen: list[tuple[str, Any]] = []

        def after(name: str, result, request: Request) -> None:
            seen.append((name, result))

        app = Wilrise()
        app.add_after_call_hook(after)

        @app.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        client = _client(app)
        client.post("/", json=_rpc("add", {"a": 2, "b": 3}))
        assert seen[0] == ("add", 5)

    def test_async_after_hook(self) -> None:
        """Async after-call hook is properly awaited."""
        seen: list[str] = []

        async def async_after(name: str, result, request: Request) -> None:
            seen.append(name)

        app = Wilrise()
        app.add_after_call_hook(async_after)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        client = _client(app)
        client.post("/", json=_rpc("ping"))
        assert "ping" in seen

    def test_hook_not_called_on_method_error(self) -> None:
        """After-call hook is NOT invoked when the method raises an exception."""
        from wilrise import RpcError

        seen: list[str] = []
        app = Wilrise()
        app.add_after_call_hook(lambda name, result, req: seen.append(name))

        @app.method
        def fail() -> None:  # pyright: ignore[reportUnusedFunction]
            raise RpcError(-32001, "err")

        client = _client(app)
        client.post("/", json=_rpc("fail"))
        assert seen == []


# ---------------------------------------------------------------------------
# RpcContext and get_rpc_context (FastAPI: request context / g object)
# ---------------------------------------------------------------------------


class TestRpcContext:
    def test_get_rpc_context_in_method_via_use(self) -> None:
        """RpcContext is available in a method via Use(get_rpc_context)."""
        app = Wilrise()

        @app.method
        def ctx_method(ctx: RpcContext = Use(get_rpc_context)) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
            return {
                "method": ctx.method,
                "request_id": ctx.request_id,
                "is_notification": ctx.is_notification,
            }

        client = _client(app)
        r = client.post("/", json=_rpc("ctx_method", id=42))
        data = r.json()["result"]
        assert data["method"] == "ctx_method"
        assert data["request_id"] == 42
        assert data["is_notification"] is False

    def test_rpc_context_http_request_id_from_header(self) -> None:
        """RpcContext.http_request_id reads from X-Request-ID header."""
        app = Wilrise()

        @app.method
        def get_req_id(ctx: RpcContext = Use(get_rpc_context)) -> str:  # pyright: ignore[reportUnusedFunction]
            return ctx.http_request_id

        client = _client(app)
        r = client.post(
            "/",
            json=_rpc("get_req_id"),
            headers={"X-Request-ID": "trace-abc"},
        )
        assert r.json()["result"] == "trace-abc"

    def test_rpc_context_http_request_id_defaults_to_unknown(self) -> None:
        """When X-Request-ID header is absent, http_request_id defaults to 'unknown'."""
        app = Wilrise()

        @app.method
        def get_req_id(ctx: RpcContext = Use(get_rpc_context)) -> str:  # pyright: ignore[reportUnusedFunction]
            return ctx.http_request_id

        client = _client(app)
        r = client.post("/", json=_rpc("get_req_id"))
        assert r.json()["result"] == "unknown"


# ---------------------------------------------------------------------------
# add_request_logger (observability extension point)
# ---------------------------------------------------------------------------


class TestRequestLogger:
    def test_request_logger_called_with_context_and_duration(self) -> None:
        """add_request_logger receives (context, duration_ms, response, error)."""
        logged: list[dict[str, Any]] = []

        def my_logger(context: RpcContext, duration_ms: float, response, error) -> None:
            logged.append(
                {
                    "method": context.method if context.method else None,
                    "duration_ms": duration_ms,
                    "has_response": response is not None,
                }
            )

        app = Wilrise()
        app.add_request_logger(my_logger)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        client = _client(app)
        client.post("/", json=_rpc("ping"))
        assert len(logged) == 1
        assert logged[0]["has_response"] is True
        assert logged[0]["duration_ms"] >= 0

    def test_async_request_logger_is_awaited(self) -> None:
        logged: list[bool] = []

        async def async_logger(context, duration_ms, response, error) -> None:
            logged.append(True)

        app = Wilrise()
        app.add_request_logger(async_logger)

        @app.method
        def ping() -> str:  # pyright: ignore[reportUnusedFunction]
            return "pong"

        client = _client(app)
        client.post("/", json=_rpc("ping"))
        assert logged == [True]


# ---------------------------------------------------------------------------
# Dependency generator cleanup (yield-based dependencies)
# ---------------------------------------------------------------------------


class TestGeneratorDependency:
    def test_sync_generator_cleanup_runs(self) -> None:
        """Use provider that uses yield: finally block runs after RPC completes."""
        cleanup_log: list[str] = []

        def db_session(request: Request):
            try:
                yield "db"
            finally:
                cleanup_log.append("closed")

        app = Wilrise()

        @app.method
        def use_db(db: str = Use(db_session)) -> str:  # pyright: ignore[reportUnusedFunction]
            return db

        client = _client(app)
        r = client.post("/", json=_rpc("use_db"))
        assert r.json()["result"] == "db"
        assert cleanup_log == ["closed"]

    def test_async_generator_cleanup_runs(self) -> None:
        """Use provider with async yield: finally block runs after RPC."""
        cleanup_log: list[str] = []

        async def async_db(request: Request):
            try:
                yield "async_db"
            finally:
                cleanup_log.append("async_closed")

        app = Wilrise()

        @app.method
        async def use_db(db: str = Use(async_db)) -> str:  # pyright: ignore[reportUnusedFunction]
            return db

        client = _client(app)
        r = client.post("/", json=_rpc("use_db"))
        assert r.json()["result"] == "async_db"
        assert cleanup_log == ["async_closed"]
