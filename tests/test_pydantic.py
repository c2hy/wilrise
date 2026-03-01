"""Pydantic integration tests — covers the FastAPI request body validation pattern.

FastAPI mapping:
  def endpoint(body: MyModel)      → @app.method with BaseModel param
  Pydantic validation failure      → -32602 Invalid params + validation_errors
  response_model=MyModel           → return a BaseModel; auto dump json
  Multiple body / mixed params     → first param BaseModel + extra params
"""
# pyright: reportUnusedFunction=false

from typing import Any

from pydantic import BaseModel
from starlette.requests import Request
from starlette.testclient import TestClient
from wilrise import Use, Wilrise

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
# Single BaseModel param — whole-params style (recommended)
# ---------------------------------------------------------------------------


class AddParams(BaseModel):
    a: int
    b: int


class TestWholeParamsStyle:
    def test_whole_params_dispatched_correctly(self) -> None:
        """params dict validated as a single BaseModel (whole-params style)."""
        app = Wilrise()

        @app.method
        def add(params: AddParams) -> int:
            return params.a + params.b

        client = _client(app)
        r = client.post("/", json=_rpc("add", {"a": 3, "b": 4}))
        assert r.json()["result"] == 7

    def test_whole_params_validation_failure_returns_32602(self) -> None:
        """Wrong types in whole-params → -32602 + validation_errors."""
        app = Wilrise()

        @app.method
        def add(params: AddParams) -> int:
            return params.a + params.b

        client = _client(app)
        r = client.post("/", json=_rpc("add", {"a": "not_int", "b": 4}))
        data = r.json()
        assert data["error"]["code"] == -32602
        assert "validation_errors" in data["error"]["data"]

    def test_whole_params_missing_field_returns_32602(self) -> None:
        """BaseModel missing required field → -32602."""
        app = Wilrise()

        @app.method
        def add(params: AddParams) -> int:
            return params.a + params.b

        client = _client(app)
        r = client.post("/", json=_rpc("add", {"a": 1}))  # b missing
        assert r.json()["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# Single BaseModel param — keyed style
# ---------------------------------------------------------------------------


class TestKeyedStyle:
    def test_keyed_style_params_dispatched_correctly(self) -> None:
        """params.params (keyed) → value for param name key validated as BaseModel."""
        app = Wilrise()

        @app.method
        def add(params: AddParams) -> int:
            return params.a + params.b

        client = _client(app)
        # Keyed: {"params": {"a": 1, "b": 2}}
        r = client.post("/", json=_rpc("add", {"params": {"a": 1, "b": 2}}))
        assert r.json()["result"] == 3


# ---------------------------------------------------------------------------
# Multiple params — first is BaseModel, rest are regular / Use
# ---------------------------------------------------------------------------


class UserFilter(BaseModel):
    active: bool
    role: str


class TestMultiParamWithModel:
    def test_first_param_model_plus_use_injection(self) -> None:
        """First param BaseModel (whole-params) + second param is Use-injected."""
        app = Wilrise()

        def get_tenant(request: Request) -> str:
            return "acme"

        @app.method
        def list_users(
            filters: UserFilter, tenant: str = Use(get_tenant)
        ) -> dict[str, Any]:
            return {
                "tenant": tenant,
                "active": filters.active,
                "role": filters.role,
            }

        client = _client(app)
        r = client.post("/", json=_rpc("list_users", {"active": True, "role": "admin"}))
        data = r.json()["result"]
        assert data["tenant"] == "acme"
        assert data["active"] is True
        assert data["role"] == "admin"

    def test_multiple_model_params_each_validated_by_key(self) -> None:
        """When first param key IS present, it's validated by key."""
        app = Wilrise()

        @app.method
        def process(filters: UserFilter) -> str:
            return f"{filters.role}:{filters.active}"

        client = _client(app)
        # Provide key "filters" explicitly
        r = client.post(
            "/",
            json=_rpc("process", {"filters": {"active": False, "role": "viewer"}}),
        )
        assert r.json()["result"] == "viewer:False"


# ---------------------------------------------------------------------------
# BaseModel return value — auto model_dump
# ---------------------------------------------------------------------------


class ItemResponse(BaseModel):
    name: str
    price: float


class TestModelReturnValue:
    def test_basemodel_return_is_serialized(self) -> None:
        """Returning a BaseModel → framework calls model_dump automatically."""
        app = Wilrise()

        @app.method
        def get_item() -> ItemResponse:
            return ItemResponse(name="widget", price=9.99)

        client = _client(app)
        r = client.post("/", json=_rpc("get_item"))
        result = r.json()["result"]
        assert result["name"] == "widget"
        assert result["price"] == 9.99

    def test_nested_basemodel_return(self) -> None:
        class Inner(BaseModel):
            value: int

        class Outer(BaseModel):
            inner: Inner

        app = Wilrise()

        @app.method
        def nested() -> Outer:
            return Outer(inner=Inner(value=42))

        client = _client(app)
        r = client.post("/", json=_rpc("nested"))
        assert r.json()["result"]["inner"]["value"] == 42


# ---------------------------------------------------------------------------
# Pydantic nested model validation
# ---------------------------------------------------------------------------


class Address(BaseModel):
    street: str
    city: str


class Person(BaseModel):
    name: str
    address: Address


class TestNestedModelValidation:
    def test_nested_model_validated_correctly(self) -> None:
        app = Wilrise()

        @app.method
        def create_person(person: Person) -> dict[str, Any]:
            return {"name": person.name, "city": person.address.city}

        client = _client(app)
        r = client.post(
            "/",
            json=_rpc(
                "create_person",
                {
                    "name": "Alice",
                    "address": {"street": "123 Main St", "city": "Springfield"},
                },
            ),
        )
        result = r.json()["result"]
        assert result["name"] == "Alice"
        assert result["city"] == "Springfield"

    def test_nested_model_invalid_returns_32602(self) -> None:
        app = Wilrise()

        @app.method
        def create_person(person: Person) -> dict[str, Any]:
            return {}

        client = _client(app)
        r = client.post(
            "/",
            json=_rpc(
                "create_person",
                # Missing address.city
                {"name": "Alice", "address": {"street": "123 Main St"}},
            ),
        )
        assert r.json()["error"]["code"] == -32602
