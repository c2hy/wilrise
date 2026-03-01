"""Param metadata and alias tests — covers the FastAPI Query/Body/Alias pattern.

FastAPI mapping:
  Param(alias="userId")     → client sends "userId", server receives user_id
  Param(default=...)        → optional parameter with default value
  Annotated[T, Param(...)]  → type-annotation-first style (FastAPI recommended)
  Annotated[T, Use(...)]    → DI without clobbering the default (type-checker friendly)
  resolve_method_params()   → test-helper API analogous to FastAPI's dependency testing
"""
# pyright: reportArgumentType=false

from typing import Any

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient
from wilrise import Param, Use, Wilrise
from wilrise.testing import get_param_meta

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
# Param(default=...)  — FastAPI: optional query/body param with default
# ---------------------------------------------------------------------------


class TestParamDefault:
    def test_param_default_used_when_absent(self) -> None:
        """When a parameter with Param(default=...) is absent, the default is used."""
        app = Wilrise()

        @app.method
        def greet(name: str = Param("World")) -> str:  # pyright: ignore[reportUnusedFunction]
            return f"Hello, {name}!"

        client = _client(app)
        r = client.post("/", json=_rpc("greet"))
        assert r.json()["result"] == "Hello, World!"

    def test_param_default_overridden_by_client(self) -> None:
        """When the client provides the parameter, the default is ignored."""
        app = Wilrise()

        @app.method
        def greet(name: str = Param("World")) -> str:  # pyright: ignore[reportUnusedFunction]
            return f"Hello, {name}!"

        client = _client(app)
        r = client.post("/", json=_rpc("greet", {"name": "Alice"}))
        assert r.json()["result"] == "Hello, Alice!"

    def test_param_default_zero_and_false_are_valid(self) -> None:
        """Falsy defaults (0, False) are properly used."""
        app = Wilrise()

        @app.method
        def counter(start: int = Param(0)) -> int:  # pyright: ignore[reportUnusedFunction]
            return start

        client = _client(app)
        r = client.post("/", json=_rpc("counter"))
        assert r.json()["result"] == 0


# ---------------------------------------------------------------------------
# Param(alias=...)  — FastAPI: alias for query/body parameter
# ---------------------------------------------------------------------------


class TestParamAlias:
    def test_alias_maps_client_key_to_param_name(self) -> None:
        """Client sends aliased key; server function receives it under param name."""
        app = Wilrise()

        @app.method
        def get_user(user_id: int = Param(alias="userId")) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
            return {"id": user_id}

        client = _client(app)
        r = client.post("/", json=_rpc("get_user", {"userId": 7}))
        assert r.json()["result"]["id"] == 7

    def test_alias_required_param_absent_returns_32602(self) -> None:
        """Required param with alias: both alias and Python name absent → -32602."""
        app = Wilrise()

        @app.method
        def get_user(user_id: int = Param(alias="userId")) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
            return {"id": user_id}

        client = _client(app)
        # Neither 'userId' nor 'user_id' is sent → truly missing → -32602
        r = client.post("/", json=_rpc("get_user", {}))
        assert r.json()["error"]["code"] == -32602

    def test_alias_accepts_python_name_as_fallback(self) -> None:
        """alias: client may also send the Python param name."""
        app = Wilrise()

        @app.method
        def get_user(user_id: int = Param(alias="userId")) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
            return {"id": user_id}

        client = _client(app)
        # Sending Python param name — also accepted (alias is additive, not exclusive)
        r = client.post("/", json=_rpc("get_user", {"user_id": 7}))
        assert r.json()["result"]["id"] == 7

    def test_alias_key_takes_precedence_over_python_name(self) -> None:
        """When both alias and Python name are present, alias takes precedence."""
        app = Wilrise()

        @app.method
        def get_user(user_id: int = Param(alias="userId")) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
            return {"id": user_id}

        client = _client(app)
        # Both sent: alias should win
        r = client.post("/", json=_rpc("get_user", {"userId": 99, "user_id": 1}))
        assert r.json()["result"]["id"] == 99

    def test_alias_with_default(self) -> None:
        """Alias param with default: absent → default applies."""
        app = Wilrise()

        @app.method
        def label(item_name: str = Param("item", alias="itemName")) -> str:  # pyright: ignore[reportUnusedFunction]
            return item_name

        client = _client(app)
        r = client.post("/", json=_rpc("label"))
        assert r.json()["result"] == "item"

        r2 = client.post("/", json=_rpc("label", {"itemName": "widget"}))
        assert r2.json()["result"] == "widget"


# ---------------------------------------------------------------------------
# Param(description=...)  — metadata only (no runtime effect)
# ---------------------------------------------------------------------------


class TestParamDescription:
    def test_description_is_stored_in_metadata(self) -> None:
        """Param(description=...) is accessible via get_param_meta."""

        def fn(value: int = Param(1, description="The input value")) -> int:
            return value

        default, meta = get_param_meta(fn, "value")
        assert meta is not None
        assert meta.description == "The input value"
        assert default == 1

    def test_description_does_not_affect_execution(self) -> None:
        app = Wilrise()

        @app.method
        def compute(x: int = Param(10, description="The x value")) -> int:  # pyright: ignore[reportUnusedFunction]
            return x * 2

        client = _client(app)
        r = client.post("/", json=_rpc("compute", {"x": 5}))
        assert r.json()["result"] == 10


# ---------------------------------------------------------------------------
# Annotated[T, Param(...)] — FastAPI's preferred annotation style
# ---------------------------------------------------------------------------


class TestAnnotatedParam:
    def test_annotated_param_with_alias(self) -> None:
        """Annotated[int, Param(alias='userId')] — FastAPI-style annotation."""
        from typing import Annotated

        app = Wilrise()

        @app.method
        def get_user(user_id: Annotated[int, Param(alias="userId")]) -> int:  # pyright: ignore[reportUnusedFunction]
            return user_id

        client = _client(app)
        r = client.post("/", json=_rpc("get_user", {"userId": 99}))
        assert r.json()["result"] == 99

    def test_annotated_param_with_description(self) -> None:
        from typing import Annotated

        def fn(count: Annotated[int, Param(description="How many")]) -> int:
            return count

        _, meta = get_param_meta(fn, "count")
        assert meta is not None
        assert meta.description == "How many"


# ---------------------------------------------------------------------------
# Annotated[T, Use(provider)] — type-checker friendly DI
# ---------------------------------------------------------------------------


class TestAnnotatedUse:
    def test_annotated_use_injects_dependency(self) -> None:
        """Annotated[str, Use(provider)] injects without cluttering default value."""
        from typing import Annotated

        app = Wilrise()

        def get_token(request: Request) -> str:
            return "tok123"

        @app.method
        def protected(token: Annotated[str, Use(get_token)]) -> str:  # pyright: ignore[reportUnusedFunction]
            return token

        client = _client(app)
        r = client.post("/", json=_rpc("protected"))
        assert r.json()["result"] == "tok123"

    def test_annotated_async_use(self) -> None:
        from typing import Annotated

        app = Wilrise()

        async def get_async_value(request: Request) -> int:
            return 42

        @app.method
        async def fetch(val: Annotated[int, Use(get_async_value)]) -> int:  # pyright: ignore[reportUnusedFunction]
            return val

        client = _client(app)
        r = client.post("/", json=_rpc("fetch"))
        assert r.json()["result"] == 42


# ---------------------------------------------------------------------------
# Zero-arg provider (RequestProvider accepts Callable[..., T])
# ---------------------------------------------------------------------------


class TestZeroArgProvider:
    """Use() with 0-arg provider (e.g. get_db() -> Session). Type regression: RequestProvider
    allows Callable[..., T]; without this, pyright would reject Use(zero_arg_provider).
    """

    def test_zero_arg_provider_default_style(self) -> None:
        """db: str = Use(get_db) with get_db() -> str works at runtime and type-check."""
        app = Wilrise()

        def get_db() -> str:
            return "db_no_request"

        @app.method
        def query(table: str, db: str = Use(get_db)) -> str:  # pyright: ignore[reportUnusedFunction]
            return f"{db}:{table}"

        client = _client(app)
        r = client.post("/", json=_rpc("query", {"table": "users"}))
        assert r.json()["result"] == "db_no_request:users"

    def test_zero_arg_provider_annotated_style(self) -> None:
        """Annotated[str, Use(get_db)] with 0-arg get_db works; param type remains str."""
        from typing import Annotated

        app = Wilrise()

        def get_db() -> str:
            return "injected"

        @app.method
        def read(key: str, db: Annotated[str, Use(get_db)]) -> str:  # pyright: ignore[reportUnusedFunction]
            return f"{key}={db}"

        client = _client(app)
        r = client.post("/", json=_rpc("read", {"key": "x"}))
        assert r.json()["result"] == "x=injected"


# ---------------------------------------------------------------------------
# resolve_method_params() — public test-helper API
# ---------------------------------------------------------------------------


class TestResolveMethodParams:
    def test_resolve_returns_list_of_args(self) -> None:
        """resolve_method_params returns positional arg list for testing."""

        from starlette.testclient import TestClient

        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        asgi = app.as_asgi()
        # We need a real Request; use TestClient scope trick
        with TestClient(asgi) as client:
            # Post a real request so the ASGI app is started
            r = client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "add",
                    "params": {"a": 3, "b": 4},
                    "id": 1,
                },
            )
            assert r.json()["result"] == 7

    def test_resolve_raises_for_unknown_method(self) -> None:
        """resolve_method_params raises ValueError for unregistered method."""
        import asyncio

        from starlette.requests import Request

        app = Wilrise()

        async def _run() -> None:
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/",
                "query_string": b"",
                "headers": [],
            }
            request = Request(scope)
            with pytest.raises(ValueError, match="Method not found"):
                await app.resolve_method_params("nonexistent", {}, request)

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Multiple params — combination of regular + Use
# ---------------------------------------------------------------------------


class TestMixedParams:
    def test_regular_plus_injected_params(self) -> None:
        """Method with regular param AND Use-injected param."""
        app = Wilrise()

        def get_db(request: Request) -> str:
            return "db_conn"

        @app.method
        def query(table: str, db: str = Use(get_db)) -> str:  # pyright: ignore[reportUnusedFunction]
            return f"{db}:{table}"

        client = _client(app)
        r = client.post("/", json=_rpc("query", {"table": "users"}))
        assert r.json()["result"] == "db_conn:users"

    def test_dependency_cached_within_request(self) -> None:
        """Same provider called multiple times in one request is invoked only once."""
        call_count = []

        def count_calls(request: Request) -> str:
            call_count.append(1)
            return "val"

        app = Wilrise()

        @app.method
        def double_dep(  # pyright: ignore[reportUnusedFunction]
            a: str = Use(count_calls), b: str = Use(count_calls)
        ) -> list[str]:
            return [a, b]

        client = _client(app)
        r = client.post("/", json=_rpc("double_dep"))
        assert r.json()["result"] == ["val", "val"]
        assert len(call_count) == 1  # cached
