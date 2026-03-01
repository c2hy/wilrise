"""Validate core JSON-RPC flow (@app.method ≈ route, Use ≈ Depends)."""

from typing import Any

from starlette.requests import Request
from starlette.testclient import TestClient
from wilrise import Use, Wilrise


def test_wilrise_json_rpc_method_and_dependency_injection() -> None:
    """Register method, inject deps; POST JSON-RPC returns result."""
    app = Wilrise()

    def get_db(request: Request) -> str:
        return "injected_db"

    @app.method
    def add(a: int, b: int, db: str = Use(get_db)) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        return {"sum": a + b, "db": db}

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
    assert "error" not in data
    assert data["result"]["sum"] == 3
    assert data["result"]["db"] == "injected_db"
    assert data["id"] == 1
