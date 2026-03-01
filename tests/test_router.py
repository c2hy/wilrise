"""Router tests — covers FastAPI's APIRouter equivalent.

FastAPI mapping:
  router = APIRouter()           → router = Router()
  app.include_router(router)     → app.include_router(router)
  router.prefix = "/items"       → include_router(router, prefix="items.")
  duplicate route registration   → ValueError on include_router
"""

from typing import Any

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient
from wilrise import Router, Use, Wilrise

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
# Basic Router usage
# ---------------------------------------------------------------------------


class TestBasicRouter:
    def test_router_method_dispatched_by_app(self) -> None:
        """Methods registered on a Router are dispatched after include_router."""
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        app = Wilrise()
        app.include_router(router)

        client = _client(app)
        r = client.post("/", json=_rpc("add", {"a": 1, "b": 2}))
        assert r.json()["result"] == 3

    def test_router_method_with_custom_name(self) -> None:
        """Router methods can use @router.method('name') for explicit naming."""
        router = Router()

        @router.method("math.multiply")
        def multiply(x: int, y: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return x * y

        app = Wilrise()
        app.include_router(router)

        client = _client(app)
        r = client.post("/", json=_rpc("math.multiply", {"x": 3, "y": 4}))
        assert r.json()["result"] == 12

    def test_multiple_methods_on_same_router(self) -> None:
        """Multiple methods on one router all work after include_router."""
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        @router.method
        def sub(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a - b

        app = Wilrise()
        app.include_router(router)
        client = _client(app)

        assert client.post("/", json=_rpc("add", {"a": 5, "b": 3})).json()["result"] == 8
        assert client.post("/", json=_rpc("sub", {"a": 5, "b": 3})).json()["result"] == 2


# ---------------------------------------------------------------------------
# include_router with prefix
# ---------------------------------------------------------------------------


class TestRouterPrefix:
    def test_prefix_prepended_to_method_name(self) -> None:
        """include_router(router, prefix='math.') → methods become 'math.add' etc."""
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        app = Wilrise()
        app.include_router(router, prefix="math.")

        client = _client(app)
        # Original name 'add' is gone; must use 'math.add'
        r = client.post("/", json=_rpc("math.add", {"a": 2, "b": 3}))
        assert r.json()["result"] == 5

    def test_prefix_does_not_duplicate_method_without_prefix(self) -> None:
        """Method without prefix is not registered after include_router with prefix."""
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        app = Wilrise()
        app.include_router(router, prefix="math.")

        client = _client(app)
        r = client.post("/", json=_rpc("add", {"a": 1, "b": 2}))
        assert r.json()["error"]["code"] == -32601

    def test_multiple_routers_with_different_prefixes(self) -> None:
        """Multiple routers with distinct prefixes coexist on the same app."""
        users = Router()
        items = Router()

        @users.method("get")
        def get_user(user_id: int) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
            return {"user": user_id}

        @items.method("get")
        def get_item(item_id: int) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
            return {"item": item_id}

        app = Wilrise()
        app.include_router(users, prefix="users.")
        app.include_router(items, prefix="items.")

        client = _client(app)
        assert client.post("/", json=_rpc("users.get", {"user_id": 1})).json()["result"] == {"user": 1}
        assert client.post("/", json=_rpc("items.get", {"item_id": 2})).json()["result"] == {"item": 2}


# ---------------------------------------------------------------------------
# Duplicate method detection
# ---------------------------------------------------------------------------


class TestRouterDuplicateDetection:
    def test_duplicate_name_raises_value_error(self) -> None:
        """Registering the same name twice → ValueError."""
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        app = Wilrise()
        app.include_router(router)

        # Including the same router again → duplicate 'add'
        with pytest.raises(ValueError, match="Duplicate method name"):
            app.include_router(router)

    def test_duplicate_prefixed_name_raises_value_error(self) -> None:
        """Prefixed duplicate also raises ValueError."""
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return a + b

        app = Wilrise()
        app.include_router(router, prefix="math.")
        with pytest.raises(ValueError, match="Duplicate method name"):
            app.include_router(router, prefix="math.")


# ---------------------------------------------------------------------------
# Dependency injection on router methods
# ---------------------------------------------------------------------------


class TestRouterWithDI:
    def test_router_method_with_use_dependency(self) -> None:
        """Methods on a Router can use Use() for dependency injection."""
        router = Router()

        def get_db(request: Request) -> str:
            return "db_conn"

        @router.method
        def query(table: str, db: str = Use(get_db)) -> str:  # pyright: ignore[reportUnusedFunction]
            return f"{db}:{table}"

        app = Wilrise()
        app.include_router(router)

        client = _client(app)
        r = client.post("/", json=_rpc("query", {"table": "users"}))
        assert r.json()["result"] == "db_conn:users"

    def test_router_method_with_prefix_and_use(self) -> None:
        """Prefixed router method with Use() works end-to-end."""
        router = Router()

        def get_service(request: Request) -> str:
            return "svc"

        @router.method
        def status(svc: str = Use(get_service)) -> str:  # pyright: ignore[reportUnusedFunction]
            return svc

        app = Wilrise()
        app.include_router(router, prefix="health.")

        client = _client(app)
        r = client.post("/", json=_rpc("health.status"))
        assert r.json()["result"] == "svc"
