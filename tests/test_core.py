"""JSON-RPC core logic and end-to-end tests."""

# pyright: reportArgumentType=none, reportRedeclaration=none, reportPrivateUsage=none, reportUnusedFunction=none
# Tests access _methods, _resolve_params; reportUnusedFunction for test helpers.

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, cast

import pytest
from starlette.requests import Request
from starlette.responses import Response
from starlette.testclient import TestClient
from wilrise import (
    BeforeCallHook,
    Param,
    Router,
    RpcContext,
    RpcError,
    Use,
    Wilrise,
    get_rpc_context,
)
from wilrise.testing import get_param_meta

# ---------------------------------------------------------------------------
# Param
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# RpcError
# ---------------------------------------------------------------------------


class TestRpcError:
    """RpcError application error and validation."""

    def test_rpc_error_valid_code(self) -> None:
        e = RpcError(-32001, "Denied", data={"x": 1})
        assert e.code == -32001
        assert e.message == "Denied"
        assert e.data == {"x": 1}

    def test_rpc_error_code_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="Application error code must be"):
            RpcError(-32603, "Internal")  # reserved
        with pytest.raises(ValueError, match="Application error code must be"):
            RpcError(-32100, "Too low")


class TestParam:
    """Param dataclass and __repr__."""

    def test_param_with_default(self) -> None:
        p = Param(1, description="first number", alias=None)
        assert p.default == 1
        assert p.description == "first number"
        assert p.alias is None
        assert "default=1" in repr(p)

    def test_param_without_default(self) -> None:
        p = Param(..., description="required", alias="foo")
        assert p.default is ...
        assert p.description == "required"
        assert p.alias == "foo"
        assert "description=" in repr(p)
        assert "alias=" in repr(p)


# ---------------------------------------------------------------------------
# get_param_meta (testing helper)
# ---------------------------------------------------------------------------


class TestGetParamMeta:
    """Extract Param metadata from parameter annotation and default."""

    def test_no_default_no_annotated(self) -> None:
        def fn(a: int) -> None:
            pass

        default, meta = get_param_meta(fn, "a")
        assert default is ...
        assert meta is None

    def test_default_is_param_instance(self) -> None:
        def fn(a: int = Param(10, description="default 10")) -> None:
            pass

        default, meta = get_param_meta(fn, "a")
        assert default == 10
        assert meta is not None
        assert meta.default == 10
        assert meta.description == "default 10"

    def test_annotated_param_no_default(self) -> None:
        def fn(a: Annotated[int, Param(description="first number")]) -> None:
            pass

        default, meta = get_param_meta(fn, "a")
        assert default is ...
        assert meta is not None
        assert meta.description == "first number"

    def test_annotated_param_with_default_in_param(self) -> None:
        def fn(a: Annotated[int, Param(default=5, description="x")]) -> None:
            pass

        default, meta = get_param_meta(fn, "a")
        assert default == 5
        assert meta is not None
        assert meta.default == 5

    def test_annotated_param_with_alias(self) -> None:
        def fn(a: Annotated[int, Param(alias="userId", description="user ID")]) -> None:
            pass

        default, meta = get_param_meta(fn, "a")
        assert default is ...
        assert meta is not None
        assert meta.alias == "userId"

    def test_merge_default_param_and_annotated_param(self) -> None:
        """Merge when default is Param and annotation has Annotated[T, Param(...)]."""

        def fn(
            a: Annotated[int, Param(description="from Annotated")] = Param(
                3, description="from default"
            ),
        ) -> None:
            pass

        default, meta = get_param_meta(fn, "a")
        assert default == 3
        assert meta is not None
        assert meta.default == 3
        assert meta.description in ("from Annotated", "from default")


# ---------------------------------------------------------------------------
# Router and Wilrise.method / include_router
# ---------------------------------------------------------------------------


class TestRouterAndWilriseMethod:
    def test_router_method_by_function_name(self) -> None:
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:
            return a + b

        assert "add" in router._methods
        assert router._methods["add"](1, 2) == 3

    def test_router_method_by_explicit_name(self) -> None:
        router = Router()

        @router.method("getUser")
        def get_user(id: int) -> dict[str, Any]:
            return {"id": id}

        assert "getUser" in router._methods
        assert "get_user" not in router._methods
        assert router._methods["getUser"](1) == {"id": 1}

    def test_wilrise_method_by_function_name(self) -> None:
        app = Wilrise()

        @app.method
        def ping() -> str:
            return "pong"

        assert "ping" in app._methods
        assert app._methods["ping"]() == "pong"

    def test_wilrise_method_by_explicit_name(self) -> None:
        app = Wilrise()

        @app.method("customName")
        def my_impl() -> str:
            return "ok"

        assert "customName" in app._methods
        assert app._methods["customName"]() == "ok"

    def test_include_router_without_prefix(self) -> None:
        app = Wilrise()
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:
            return a + b

        app.include_router(router)
        assert "add" in app._methods
        assert app._methods["add"](1, 2) == 3

    def test_include_router_with_prefix(self) -> None:
        app = Wilrise()
        router = Router()

        @router.method
        def add(a: int, b: int) -> int:
            return a + b

        app.include_router(router, prefix="math.")
        assert "math.add" in app._methods
        assert "add" not in app._methods
        assert app._methods["math.add"](1, 2) == 3

    def test_include_router_conflict_raises(self) -> None:
        app = Wilrise()
        r1, r2 = Router(), Router()

        @r1.method
        def add(a: int, b: int) -> int:
            return a + b

        @r2.method
        def add(x: int, y: int) -> int:
            return x * y

        app.include_router(r1)
        with pytest.raises(ValueError, match="Duplicate method name"):
            app.include_router(r2)


# ---------------------------------------------------------------------------
# _resolve_params: params resolution, defaults, Use, alias
# ---------------------------------------------------------------------------


class TestResolveParams:
    async def test_dict_params(self) -> None:
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        args = await app.resolve_method_params(
            "add", {"a": 10, "b": 20}, _fake_request()
        )
        assert args == [10, 20]

    async def test_list_params(self) -> None:
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        args = await app.resolve_method_params("add", [5, 7], _fake_request())
        assert args == [5, 7]

    async def test_missing_required_raises(self) -> None:
        app = Wilrise()

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        with pytest.raises(ValueError, match="Missing required argument"):
            await app.resolve_method_params("add", {"a": 1}, _fake_request())

    async def test_default_value_used(self) -> None:
        app = Wilrise()

        @app.method
        def f(x: int = 100) -> int:
            return x

        args = await app.resolve_method_params("f", None, _fake_request())
        assert args == [100]

    async def test_param_default_used(self) -> None:
        app = Wilrise()

        @app.method
        def f(x: int = Param(42)) -> int:
            return x

        args = await app.resolve_method_params("f", {}, _fake_request())
        assert args == [42]

    async def test_use_sync_injection(self) -> None:
        app = Wilrise()
        injected: list[Request] = []

        def provide(request: Request) -> str:
            injected.append(request)
            return "injected"

        @app.method
        def f(tag: str = Use(provide)) -> str:
            return tag

        req = _fake_request()
        args = await app.resolve_method_params("f", {}, req)
        assert args == ["injected"]
        assert injected == [req]

    async def test_use_async_injection(self) -> None:
        app = Wilrise()

        async def provide_async(request: Request) -> int:
            return 99

        @app.method
        def f(n: int = Use(provide_async)) -> int:
            return n

        args = await app.resolve_method_params("f", {}, _fake_request())
        assert args == [99]

    async def test_param_alias_takes_value(self) -> None:
        app = Wilrise()

        @app.method
        def f(user_id: Annotated[int, Param(alias="userId")]) -> int:
            return user_id

        args = await app.resolve_method_params("f", {"userId": 123}, _fake_request())
        assert args == [123]

    async def test_param_alias_over_name_when_both_present(self) -> None:
        app = Wilrise()

        @app.method
        def f(x: Annotated[int, Param(alias="alias_x")]) -> int:
            return x

        # When only alias is passed, use alias value
        args = await app.resolve_method_params("f", {"alias_x": 7}, _fake_request())
        assert args == [7]

    async def test_resolve_method_params_method_not_found_raises(self) -> None:
        """resolve_method_params with unknown method raises ValueError."""
        app = Wilrise()

        @app.method
        def ping() -> str:
            return "pong"

        with pytest.raises(ValueError, match="Method not found: nonexistent"):
            await app.resolve_method_params("nonexistent", {}, _fake_request())

    async def test_use_dependency_cached_per_request(self) -> None:
        """Same Use(provider) in two params: provider called once per request."""
        app = Wilrise()
        call_count = 0

        def provide(request: Request) -> str:
            nonlocal call_count
            call_count += 1
            return "singleton"

        @app.method
        def f(
            a: str = Use(provide),
            b: str = Use(provide),
        ) -> list[str]:
            return [a, b]

        req = _fake_request()
        args = await app.resolve_method_params("f", {}, req)
        assert args == ["singleton", "singleton"]
        assert call_count == 1


# ---------------------------------------------------------------------------
# Pydantic parameter validation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    __import__("wilrise.core", fromlist=["BaseModel"]).BaseModel is None,
    reason="pydantic not installed",
)
class TestPydanticValidation:
    """Pydantic BaseModel parameter validation (optional dependency)."""

    async def test_single_param_base_model_entire_params(self) -> None:
        """Single param as BaseModel: entire params dict is validated as that model."""
        from pydantic import BaseModel

        class AddParams(BaseModel):
            a: int
            b: int

        app = Wilrise()

        @app.method
        def add(params: AddParams) -> int:
            return params.a + params.b

        args = await app.resolve_method_params(
            "add", {"a": 10, "b": 20}, _fake_request()
        )
        assert len(args) == 1
        assert isinstance(args[0], AddParams)
        assert args[0].a == 10 and args[0].b == 20
        assert args[0].model_dump() == {"a": 10, "b": 20}

    async def test_single_param_base_model_validation_failure(self) -> None:
        """Invalid params for single BaseModel param raises ParamsValidationError."""
        from pydantic import BaseModel
        from wilrise import ParamsValidationError

        class AddParams(BaseModel):
            a: int
            b: int

        app = Wilrise()

        @app.method
        def add(params: AddParams) -> int:
            return params.a + params.b

        with pytest.raises(ParamsValidationError) as exc_info:
            await app.resolve_method_params(
                "add", {"a": "not_an_int", "b": 20}, _fake_request()
            )
        errors = exc_info.value.errors
        assert isinstance(errors, list)
        assert len(errors) >= 1
        assert any("a" in str(e.get("loc", [])) for e in errors)

    async def test_named_param_base_model(self) -> None:
        """Multiple params: one param annotated with BaseModel is validated."""
        from pydantic import BaseModel

        class UserIn(BaseModel):
            name: str
            age: int

        app = Wilrise()

        @app.method
        def greet(user: UserIn, prefix: str) -> str:
            return f"{prefix}: {user.name}"

        args = await app.resolve_method_params(
            "greet",
            {"user": {"name": "Alice", "age": 30}, "prefix": "Hello"},
            _fake_request(),
        )
        assert len(args) == 2
        assert isinstance(args[0], UserIn)
        assert args[0].name == "Alice" and args[0].age == 30
        assert args[1] == "Hello"

    async def test_annotated_base_model_param(self) -> None:
        """Annotated[MyModel, Param(...)] is still validated as BaseModel."""
        from typing import Annotated

        from pydantic import BaseModel
        from wilrise.core import Param

        class Data(BaseModel):
            x: int

        app = Wilrise()

        @app.method
        def f(data: Annotated[Data, Param(description="payload")]) -> int:
            return data.x

        args = await app.resolve_method_params(
            "f", {"data": {"x": 42}}, _fake_request()
        )
        assert len(args) == 1
        assert isinstance(args[0], Data)
        assert args[0].x == 42

    async def test_first_param_base_model_key_absent_rest_by_use_or_default(
        self,
    ) -> None:
        """First param is BaseModel and key absent: entire params as that model;
        rest are resolved by key/Use/default (e.g. params + db + user_id)."""
        from pydantic import BaseModel

        from wilrise import Use

        class CreateEmotionRequest(BaseModel):
            emotion: str

        app = Wilrise()
        injected: list[object] = []

        def get_db(request: Request) -> str:
            injected.append(request)
            return "db_session"

        def get_user_id(request: Request) -> str:
            return "user_42"

        @app.method
        def create_emotion(
            params: CreateEmotionRequest,
            db: str = Use(get_db),
            user_id: str = Use(get_user_id),
        ) -> dict:
            return {
                "emotion": params.emotion,
                "db": db,
                "user_id": user_id,
            }

        # Client sends params without key "params" (whole body is the payload).
        req = _fake_request()
        args = await app.resolve_method_params(
            "create_emotion", {"emotion": "happy"}, req
        )
        assert len(args) == 3
        assert isinstance(args[0], CreateEmotionRequest)
        assert args[0].emotion == "happy"
        assert args[1] == "db_session"
        assert args[2] == "user_42"
        assert injected == [req]

    async def test_first_param_base_model_key_present_still_by_key(self) -> None:
        """When first param's key is present, use value for that key (existing)."""
        from pydantic import BaseModel

        class Payload(BaseModel):
            x: int

        app = Wilrise()

        @app.method
        def f(params: Payload, suffix: str = "!") -> str:
            return f"{params.x}{suffix}"

        args = await app.resolve_method_params(
            "f", {"params": {"x": 10}, "suffix": "?"}, _fake_request()
        )
        assert len(args) == 2
        assert isinstance(args[0], Payload)
        assert args[0].x == 10
        assert args[1] == "?"

    def test_e2e_pydantic_valid_params(self) -> None:
        """E2E: valid params for single BaseModel param returns result."""
        from pydantic import BaseModel

        app = Wilrise()

        class AddParams(BaseModel):
            a: int
            b: int

        @app.method
        def add(params: AddParams) -> int:
            return params.a + params.b

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 1, "b": 2},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["result"] == 3
        assert data["id"] == 1

    def test_e2e_pydantic_invalid_params_returns_32602(self) -> None:
        """E2E: invalid params for BaseModel returns -32602 with validation_errors."""
        from pydantic import BaseModel

        app = Wilrise()

        class AddParams(BaseModel):
            a: int
            b: int

        @app.method
        def add(params: AddParams) -> int:
            return params.a + params.b

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": "x", "b": "y"},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32602
        assert data["error"]["message"] == "Invalid params"
        assert "validation_errors" in data["error"]["data"]
        raw_errors = data["error"]["data"]["validation_errors"]
        assert isinstance(raw_errors, list)
        errors: list[Any] = cast(list[Any], raw_errors)
        assert len(errors) >= 1


def _fake_request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [],
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# _handle_request / ASGI end-to-end
# ---------------------------------------------------------------------------


class TestHandleRequest:
    """Exercise as_asgi() app via TestClient; cover various requests and errors."""

    @pytest.fixture
    def app(self) -> Wilrise:
        w = Wilrise()

        @w.method
        def add(a: int, b: int) -> int:
            return a + b

        @w.method
        async def add_async(a: int, b: int) -> int:
            return a + b

        @w.method
        def fail() -> None:
            raise ValueError("expected error")

        return w

    @pytest.fixture
    def client(self, app: Wilrise) -> TestClient:
        return TestClient(app.as_asgi())

    def test_post_success_sync(self, client: TestClient) -> None:
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 1, "b": 2},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["jsonrpc"] == "2.0"
        assert data["result"] == 3
        assert data["id"] == 1

    def test_post_success_async(self, client: TestClient) -> None:
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add_async",
                "params": {"a": 3, "b": 4},
                "id": 2,
            },
        )
        assert r.status_code == 200
        assert r.json()["result"] == 7
        assert r.json()["id"] == 2

    def test_post_positional_params(self, client: TestClient) -> None:
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": [10, 20],
                "id": 3,
            },
        )
        assert r.status_code == 200
        assert r.json()["result"] == 30

    def test_non_post_returns_405(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 405
        # Starlette may reject GET at routing layer; body may be plain text
        if "application/json" in (r.headers.get("content-type") or ""):
            data = r.json()
            assert data["error"]["code"] == -32600
            assert "Invalid Request" in data["error"]["message"]

    def test_invalid_json_parse_error(self, client: TestClient) -> None:
        r = client.post(
            "/",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400
        data = r.json()
        assert data["error"]["code"] == -32700
        assert "Parse error" in data["error"]["message"]

    def test_body_not_object_nor_array_invalid_request(
        self, client: TestClient
    ) -> None:
        """Body not a dict and not array (e.g. string) → -32600, 400."""
        r = client.post(
            "/",
            content=b'"string"',
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400
        data = r.json()
        assert data["error"]["code"] == -32600

    def test_missing_method_invalid_request(self, client: TestClient) -> None:
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "params": {}, "id": 1},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32600

    def test_method_not_found(self, client: TestClient) -> None:
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "nonexistent",
                "params": {},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32601
        assert "Method not found" in data["error"]["message"]
        assert data["error"]["data"] == {"method": "nonexistent"}

    def test_reserved_method_name_rpc_prefix(self, client: TestClient) -> None:
        """Method names starting with rpc. are reserved (JSON-RPC 2.0 §8) → -32600."""
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "rpc.foo",
                "params": {},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32600
        assert "Invalid Request" in data["error"]["message"]
        assert data["error"]["data"]["method"] == "rpc.foo"
        assert data["error"]["data"]["reason"] == "reserved_method_name"

    def test_internal_error_from_exception(self, client: TestClient) -> None:
        """With debug=True, full exception message and type are returned."""
        w = Wilrise(debug=True)

        @w.method
        def fail() -> None:
            raise ValueError("expected error")

        c = TestClient(w.as_asgi())
        r = c.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "fail",
                "params": {},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32603
        assert "expected error" in data["error"]["message"]
        assert data["error"]["data"]["type"] == "ValueError"

    def test_internal_error_production_hides_details(self, client: TestClient) -> None:
        """With debug=False (default), exception details are hidden for security."""
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "fail",
                "params": {},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32603
        assert data["error"]["message"] == "Internal error"
        # Production -32603 includes request_id for log correlation
        assert data["error"].get("data") is not None
        assert "request_id" in data["error"]["data"]

    def test_result_not_json_serializable_returns_32603(
        self, client: TestClient
    ) -> None:
        """Return value that cannot be JSON-serialized → -32603 with message."""
        w = Wilrise()

        @w.method
        def bad_result() -> object:
            return object()  # not JSON-serializable

        c = TestClient(w.as_asgi())
        r = c.post(
            "/",
            json={"jsonrpc": "2.0", "method": "bad_result", "params": {}, "id": 1},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32603
        assert "JSON-serializable" in data["error"]["message"]
        assert data["error"].get("data") is not None
        assert "request_id" in data["error"]["data"]

    def test_use_provider_exception_returns_32603(self) -> None:
        """Use(provider) when provider raises → -32603 Internal error."""
        app = Wilrise()

        def failing_provider(request: Request) -> None:
            raise RuntimeError("dependency failed")

        @app.method
        def need_dep(x: str = Use(failing_provider)) -> str:  # type: ignore[assignment]
            return x

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "need_dep", "params": {}, "id": 1},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32603
        assert data["error"]["message"] == "Internal error"
        assert data["error"].get("data") is not None
        assert "request_id" in data["error"]["data"]

    def test_rpc_error_from_method_returns_application_error(self) -> None:
        """Method raises RpcError(-32001, ...) → response has code -32001 and data."""
        app = Wilrise()

        @app.method
        def need_auth(user_id: int) -> dict[str, Any]:
            raise RpcError(
                -32001,
                "Permission denied",
                data={"resource": "user", "user_id": user_id},
            )

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "need_auth",
                "params": {"user_id": 42},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32001
        assert data["error"]["message"] == "Permission denied"
        assert data["error"]["data"] == {"resource": "user", "user_id": 42}
        assert data["id"] == 1

    def test_rpc_error_from_use_provider_returns_application_error(self) -> None:
        """Use(provider) raises RpcError → response has application error code."""
        app = Wilrise()

        def auth_provider(request: Request) -> str:
            raise RpcError(-32000, "Unauthorized", data={"reason": "missing_token"})

        @app.method
        def secret(x: str = Use(auth_provider)) -> str:  # type: ignore[assignment]
            return x

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "secret", "params": {}, "id": 1},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32000
        assert data["error"]["message"] == "Unauthorized"
        assert data["error"]["data"] == {"reason": "missing_token"}

    def test_missing_required_param_invalid_params(self, client: TestClient) -> None:
        """Missing required param → -32602 Invalid params; unified validation_errors."""
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 1},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32602
        assert "Invalid params" in data["error"]["message"]
        assert "validation_errors" in data["error"]["data"]
        errors = data["error"]["data"]["validation_errors"]
        assert len(errors) == 1
        assert errors[0]["loc"] == ["b"]
        assert "Missing required argument" in errors[0]["msg"]

    def test_notification_no_response(self, client: TestClient) -> None:
        """Notification (no id) → 204 No Content, no body (JSON-RPC 2.0 §4.1)."""
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "add", "params": {"a": 1, "b": 2}},
        )
        assert r.status_code == 204
        assert r.content in (b"", b"null")

    def test_id_null_echoed_in_response(self, client: TestClient) -> None:
        """Request with "id": null → response echoes id: null (not a notification)."""
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 1, "b": 2},
                "id": None,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["id"] is None
        assert data["result"] == 3

    def test_id_preserved_in_success(self, client: TestClient) -> None:
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 1, "b": 2},
                "id": "req-1",
            },
        )
        assert r.status_code == 200
        assert r.json()["id"] == "req-1"

    def test_method_not_string_invalid_request(self, client: TestClient) -> None:
        """JSON-RPC 2.0: method MUST be a String. method: 1 → -32600."""
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": 1, "params": [], "id": 1},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32600
        assert data["id"] == 1

    def test_params_not_structured_invalid_request(self, client: TestClient) -> None:
        """params when present MUST be Array or Object; string → -32600."""
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": "bar",
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32600
        assert "Invalid Request" in data["error"]["message"]

    def test_jsonrpc_version_invalid_request(self, client: TestClient) -> None:
        """Request with jsonrpc != "2.0" or missing → -32600."""
        r = client.post(
            "/",
            json={"method": "add", "params": {"a": 1, "b": 2}, "id": 1},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32600

    def test_id_zero_preserved_in_response(self, client: TestClient) -> None:
        """id MAY be Number. id: 0 must be echoed in response."""
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 1, "b": 2},
                "id": 0,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("id") == 0
        assert data.get("result") == 3

    # -----------------------------------------------------------------------
    # Batch (JSON-RPC 2.0 §6)
    # -----------------------------------------------------------------------

    def test_batch_empty_array_invalid_request(self, client: TestClient) -> None:
        """Batch empty array [] → single Response -32600, 400."""
        r = client.post("/", json=[])
        assert r.status_code == 400
        data = r.json()
        assert data["error"]["code"] == -32600
        assert data["id"] is None

    def test_batch_invalid_element_returns_error_response(
        self, client: TestClient
    ) -> None:
        """Batch [1] → array with one error Response -32600."""
        r = client.post("/", json=[1])
        assert r.status_code == 200
        raw = r.json()
        assert isinstance(raw, list)
        data: list[dict[str, Any]] = cast(list[dict[str, Any]], raw)
        assert len(data) == 1
        assert data[0]["error"]["code"] == -32600
        assert data[0]["id"] is None

    def test_batch_multiple_invalid_elements(self, client: TestClient) -> None:
        """Batch [1, 2, 3] → array of three error Responses."""
        r = client.post("/", json=[1, 2, 3])
        assert r.status_code == 200
        raw = r.json()
        assert isinstance(raw, list)
        data: list[dict[str, Any]] = cast(list[dict[str, Any]], raw)
        assert len(data) == 3
        for item in data:
            assert item["error"]["code"] == -32600
            assert item["id"] is None

    def test_batch_mixed_requests(self, client: TestClient) -> None:
        """Batch with success + notification + invalid → responses (no notif)."""
        r = client.post(
            "/",
            json=[
                {"jsonrpc": "2.0", "method": "add", "params": [1, 2], "id": "1"},
                {"jsonrpc": "2.0", "method": "add", "params": [3, 4]},
                {"foo": "bar"},
            ],
        )
        assert r.status_code == 200
        raw = r.json()
        assert isinstance(raw, list)
        data: list[dict[str, Any]] = cast(list[dict[str, Any]], raw)
        assert len(data) == 2
        assert data[0]["result"] == 3
        assert data[0]["id"] == "1"
        assert data[1]["error"]["code"] == -32600
        assert data[1]["id"] is None

    def test_batch_all_notifications_no_content(self, client: TestClient) -> None:
        """Batch with only notifications → 204 No Content, no body."""
        r = client.post(
            "/",
            json=[
                {"jsonrpc": "2.0", "method": "add", "params": [1, 2]},
                {"jsonrpc": "2.0", "method": "add", "params": [3, 4]},
            ],
        )
        assert r.status_code == 204
        assert r.content in (b"", b"null")

    def test_batch_multiple_success(self, client: TestClient) -> None:
        """Batch with multiple valid requests → array of results."""
        r = client.post(
            "/",
            json=[
                {"jsonrpc": "2.0", "method": "add", "params": [1, 2], "id": 1},
                {"jsonrpc": "2.0", "method": "add", "params": [10, 20], "id": 2},
            ],
        )
        assert r.status_code == 200
        raw = r.json()
        assert isinstance(raw, list)
        data: list[dict[str, Any]] = cast(list[dict[str, Any]], raw)
        assert len(data) == 2
        assert data[0]["result"] == 3
        assert data[0]["id"] == 1
        assert data[1]["result"] == 30
        assert data[1]["id"] == 2


# ---------------------------------------------------------------------------
# Security and limits (debug, max_batch_size, max_request_size)
# ---------------------------------------------------------------------------


class TestSecurityAndLimits:
    """Test debug mode, batch size limit, and request size limit."""

    def test_max_request_size_exceeded(self) -> None:
        """Request body larger than max_request_size returns 413."""
        app = Wilrise(max_request_size=10)

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 1, "b": 2},
                "id": 1,
            },
        )
        assert r.status_code == 413
        data = r.json()
        assert data["error"]["code"] == -32600
        assert "Request body too large" in data["error"]["message"]

    def test_max_batch_size_exceeded(self) -> None:
        """Batch with more than max_batch_size requests returns 400."""
        app = Wilrise(max_batch_size=3)

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json=[
                {"jsonrpc": "2.0", "method": "add", "params": [1, 2], "id": 1},
                {"jsonrpc": "2.0", "method": "add", "params": [3, 4], "id": 2},
                {"jsonrpc": "2.0", "method": "add", "params": [5, 6], "id": 3},
                {"jsonrpc": "2.0", "method": "add", "params": [7, 8], "id": 4},
            ],
        )
        assert r.status_code == 400
        data = r.json()
        assert data["error"]["code"] == -32600
        assert data["error"]["data"]["reason"] == "batch_size_exceeded"
        assert data["error"]["data"]["batch_size"] == 4
        assert data["error"]["data"]["max_batch_size"] == 3


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class TestAsAsgiAndMount:
    """Test as_asgi(path) and mount(app, path)."""

    def test_as_asgi_default_path(self) -> None:
        """as_asgi() defaults to path '/' (existing behavior)."""
        app = Wilrise()

        @app.method
        def ping() -> int:
            return 1

        asgi = app.as_asgi()
        r = TestClient(asgi).post(
            "/", json={"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1}
        )
        assert r.status_code == 200
        assert r.json()["result"] == 1

    def test_as_asgi_custom_path(self) -> None:
        """as_asgi(path='/rpc') serves JSON-RPC at /rpc."""
        app = Wilrise()

        @app.method
        def get_value() -> int:
            return 42

        asgi = app.as_asgi(path="/rpc")
        client = TestClient(asgi)
        r = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "method": "get_value", "params": {}, "id": 1},
        )
        assert r.status_code == 200
        assert r.json()["result"] == 42
        r_root = client.post(
            "/", json={"jsonrpc": "2.0", "method": "get_value", "params": {}, "id": 1}
        )
        assert r_root.status_code == 404

    def test_mount_adds_route_to_existing_app(self) -> None:
        """mount(starlette_app, path) adds POST route to existing app."""
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        def health(_: Any) -> PlainTextResponse:
            return PlainTextResponse("ok")

        starlette_app = Starlette(
            routes=[Route("/health", health, methods=["GET"])],
        )
        wilrise = Wilrise()

        @wilrise.method
        def get_99() -> int:
            return 99

        wilrise.mount(starlette_app, path="/rpc")
        client = TestClient(starlette_app)
        r_health = client.get("/health")
        assert r_health.status_code == 200
        assert r_health.text == "ok"
        r_rpc = client.post(
            "/rpc",
            json={"jsonrpc": "2.0", "method": "get_99", "params": {}, "id": 1},
        )
        assert r_rpc.status_code == 200
        assert r_rpc.json()["result"] == 99


class TestRpcHooks:
    """Test before_call and after_call RPC hooks."""

    def test_before_call_returning_error_short_circuits(self) -> None:
        """before_call returning a dict sends that error and skips method."""
        from wilrise import BeforeCallHook
        from wilrise.protocol import build_error

        app = Wilrise()

        def deny(_method: str, _params: Any, _request: Request) -> dict[str, Any]:
            return build_error(-32001, "Permission denied", None)

        app.add_before_call_hook(cast(BeforeCallHook, deny))

        @app.method
        def secret() -> str:
            return "never_reached"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "secret", "params": {}, "id": 1},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32001
        assert data["error"]["message"] == "Permission denied"

    def test_before_call_returning_none_proceeds(self) -> None:
        """before_call returning None lets the method run."""
        from wilrise import BeforeCallHook

        app = Wilrise()
        seen: list[str] = []

        def allow(method: str, _params: Any, _request: Request) -> None:
            seen.append(method)

        app.add_before_call_hook(cast(BeforeCallHook, allow))

        @app.method
        def ping() -> str:
            return "pong"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1},
        )
        assert r.status_code == 200
        assert r.json()["result"] == "pong"
        assert seen == ["ping"]

    def test_after_call_receives_result(self) -> None:
        """after_call is called with method_name, result, request after success."""
        from wilrise import AfterCallHook

        app = Wilrise()
        log: list[tuple[str, Any]] = []

        def log_result(method: str, result: Any, _request: Request) -> None:
            log.append((method, result))

        app.add_after_call_hook(cast(AfterCallHook, log_result))

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 1, "b": 2},
                "id": 1,
            },
        )
        assert r.status_code == 200
        assert r.json()["result"] == 3
        assert log == [("add", 3)]


class TestMiddleware:
    """Test add_middleware integration."""

    def test_middleware_runs_before_endpoint(self) -> None:
        """Custom middleware can add headers to response."""
        from starlette.middleware.base import BaseHTTPMiddleware

        header_values: list[str] = []

        class AddHeaderMiddleware(BaseHTTPMiddleware):
            async def dispatch(
                self,
                request: Request,
                call_next: Callable[[Request], Awaitable[Response]],
            ) -> Response:
                header_values.append("before")
                response = await call_next(request)
                response.headers["X-Custom"] = "added"
                return response

        app = Wilrise()

        @app.method
        def ping() -> str:
            return "pong"

        app.add_middleware(AddHeaderMiddleware)
        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1},
        )
        assert r.status_code == 200
        assert r.json()["result"] == "pong"
        assert r.headers.get("X-Custom") == "added"
        assert header_values == ["before"]


# ---------------------------------------------------------------------------
# Use marker
# ---------------------------------------------------------------------------


class TestUse:
    def test_use_call_invokes_provider(self) -> None:
        def provider() -> str:
            return "ok"

        u = Use(provider)
        assert u() == "ok"


# ---------------------------------------------------------------------------
# Integration: Router + prefix + Use (aligned with examples/main.py)
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration scenarios aligned with the example app."""

    def test_router_prefix_and_use_e2e(self) -> None:
        """Router with prefix and method with Use injection; call via HTTP."""
        app = Wilrise()
        math_router = Router()

        @math_router.method
        async def add(
            a: Annotated[int, Param(description="first addend")],
            b: Annotated[int, Param(description="second addend")],
        ) -> int:
            return a + b

        class DBSession:
            async def get_user(self, user_id: int) -> dict[str, Any] | None:
                return {1: {"id": 1, "name": "Alice"}, 2: {"id": 2, "name": "Bob"}}.get(
                    user_id
                )

        async def get_db_session(request: Request) -> DBSession:
            return DBSession()

        app.include_router(math_router, prefix="math.")

        @app.method
        async def get_user(
            user_id: int, db: DBSession = Use(get_db_session)
        ) -> dict[str, Any] | None:
            return await db.get_user(user_id)

        client = TestClient(app.as_asgi())

        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "math.add",
                "params": {"a": 1, "b": 2},
                "id": 1,
            },
        )
        assert r.status_code == 200
        assert r.json()["result"] == 3
        assert r.json()["id"] == 1

        r2 = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "get_user",
                "params": {"user_id": 1},
                "id": 2,
            },
        )
        assert r2.status_code == 200
        assert r2.json()["result"] == {"id": 1, "name": "Alice"}

    def test_param_alias_in_request(self) -> None:
        """RPC client passes params via Param alias (e.g. userId)."""
        app = Wilrise()

        @app.method
        async def get_user_by_alias(
            user_id: Annotated[int, Param(alias="userId", description="user ID")],
        ) -> dict[str, Any]:
            return {"user_id": user_id}

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "get_user_by_alias",
                "params": {"userId": 42},
                "id": 1,
            },
        )
        assert r.status_code == 200
        assert r.json()["result"]["user_id"] == 42


# ---------------------------------------------------------------------------
# RpcContext and get_rpc_context
# ---------------------------------------------------------------------------


class TestRpcContext:
    """RpcContext is set on request.state and get_rpc_context is injectable."""

    def test_rpc_context_available_in_before_call_hook(self) -> None:
        app = Wilrise()
        seen: list[RpcContext] = []

        def capture_ctx(_method: str, _params: Any, request: Request) -> None:
            ctx = getattr(request.state, "rpc_context", None)
            if ctx is not None:
                seen.append(ctx)

        app.add_before_call_hook(cast(BeforeCallHook, capture_ctx))

        @app.method
        def ping() -> str:
            return "pong"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 99},
        )
        assert r.status_code == 200
        assert len(seen) == 1
        assert seen[0].method == "ping"
        assert seen[0].request_id == 99
        assert seen[0].is_notification is False

    def test_get_rpc_context_in_method(self) -> None:
        app = Wilrise()

        @app.method
        def echo_id(ctx: RpcContext | None = Use(get_rpc_context)) -> Any:
            return ctx.request_id if ctx else None

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "echo_id", "params": {}, "id": 42},
        )
        assert r.status_code == 200
        assert r.json()["result"] == 42


# ---------------------------------------------------------------------------
# Extension points: ExceptionMapper
# ---------------------------------------------------------------------------


class TestExceptionMapper:
    """Custom exception mapper maps exceptions to RPC errors."""

    def test_exception_mapper_used_when_set(self) -> None:
        class MyMapper:
            def map_exception(
                self, exc: Exception, context: RpcContext
            ) -> tuple[int, str, Any] | None:
                if isinstance(exc, ValueError):
                    return (-32002, "Bad value", {"detail": str(exc)})
                return None

        app = Wilrise()
        app.set_exception_mapper(MyMapper())

        @app.method
        def raise_value_error() -> None:
            raise ValueError("invalid")

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "method": "raise_value_error",
                "params": {},
                "id": 1,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["error"]["code"] == -32002
        assert data["error"]["message"] == "Bad value"
        assert data["error"]["data"] == {"detail": "invalid"}


# ---------------------------------------------------------------------------
# Lifespan: add_startup / add_shutdown, as_asgi passes lifespan
# ---------------------------------------------------------------------------


class TestLifespan:
    """Startup and shutdown hooks run when using as_asgi()."""

    def test_lifespan_startup_shutdown_run(self) -> None:
        started: list[str] = []
        stopped: list[str] = []

        def on_start() -> None:
            started.append("ok")

        def on_stop() -> None:
            stopped.append("ok")

        app = Wilrise()
        app.add_startup(on_start)
        app.add_shutdown(on_stop)

        @app.method
        def ping() -> str:
            return "pong"

        asgi_app = app.as_asgi()
        with TestClient(asgi_app) as client:
            r = client.post(
                "/",
                json={"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1},
            )
            assert r.status_code == 200
            assert r.json()["result"] == "pong"
        assert started == ["ok"]
        assert stopped == ["ok"]


# ---------------------------------------------------------------------------
# Background tasks: request.state.background_tasks, scheduled before return
# ---------------------------------------------------------------------------


class TestBackgroundTasks:
    """request.state.background_tasks exists and is scheduled before response return."""

    def test_background_tasks_appended_and_request_succeeds(self) -> None:
        """Appending to request.state.background_tasks does not break the request."""
        app = Wilrise()

        @app.method
        def ping(ctx: RpcContext | None = Use(get_rpc_context)) -> str:
            if ctx and ctx.request:
                tasks = getattr(ctx.request.state, "background_tasks", [])

                async def noop() -> None:
                    pass

                tasks.append(noop)
            return "pong"

        with TestClient(app.as_asgi()) as client:
            r = client.post(
                "/",
                json={"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1},
            )
            assert r.status_code == 200
            assert r.json()["result"] == "pong"


# ---------------------------------------------------------------------------
# Logger and log_level
# ---------------------------------------------------------------------------


class TestLoggerAndLogLevel:
    """Wilrise(logger=..., log_level=...) uses the given logger and level."""

    def test_custom_logger_receives_request_log(self) -> None:
        """When logger is provided, that logger receives the request completion log."""
        log_records: list[logging.LogRecord] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        custom = logging.getLogger("test.wilrise.custom")
        custom.handlers.clear()
        custom.addHandler(CaptureHandler())
        custom.setLevel(logging.DEBUG)
        app = Wilrise(logger=custom)

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        with TestClient(app.as_asgi()) as client:
            client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "add",
                    "params": {"a": 1, "b": 2},
                    "id": 1,
                },
            )
        assert len(log_records) >= 1
        assert any(r.levelno == logging.INFO for r in log_records)

    def test_log_level_warning_suppresses_info_still_emits_error(self) -> None:
        """When log_level=WARNING, INFO suppressed; ERROR (exception) still emitted."""
        log_records: list[logging.LogRecord] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        custom = logging.getLogger("test.wilrise.level")
        custom.handlers.clear()
        custom.addHandler(CaptureHandler())
        custom.setLevel(logging.DEBUG)
        app = Wilrise(logger=custom, log_level=logging.WARNING)

        @app.method
        def add(a: int, b: int) -> int:
            return a + b

        @app.method
        def fail() -> str:
            raise RuntimeError("oops")

        with TestClient(app.as_asgi()) as client:
            client.post(
                "/",
                json={
                    "jsonrpc": "2.0",
                    "method": "add",
                    "params": {"a": 1, "b": 2},
                    "id": 1,
                },
            )
        assert not any(r.levelno == logging.INFO for r in log_records), (
            "INFO should be suppressed"
        )
        log_records.clear()
        with TestClient(app.as_asgi()) as client:
            client.post(
                "/",
                json={"jsonrpc": "2.0", "method": "fail", "params": {}, "id": 2},
            )
        assert any(r.levelno == logging.ERROR for r in log_records), (
            "ERROR should be emitted"
        )
