"""End-to-end tests for the introductory examples (01 to 04).

These tests ensure the documented step-by-step examples remain fully
functional and aren't broken by framework updates.
"""

import importlib
import sys
from pathlib import Path
from typing import Any

# Allow running from repo root or examples/ dir
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from starlette.testclient import TestClient


def rpc(
    method: str,
    params: dict[str, Any] | list[Any] | None = None,
    id: int = 1,
) -> dict[str, Any]:
    req: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        req["params"] = params
    return req


def get_client(module_name: str) -> TestClient:
    """Dynamically load an example module and return a TestClient for its `app`."""
    mod = importlib.import_module(module_name)
    return TestClient(mod.app.as_asgi())


# ---------------------------------------------------------------------------
# 01_minimal.py
# ---------------------------------------------------------------------------
def test_01_minimal_add_named() -> None:
    client = get_client("01_minimal")
    r = client.post("/", json=rpc("add", {"a": 3, "b": 4}))
    assert r.status_code == 200
    assert r.json()["result"] == 7


def test_01_minimal_add_positional() -> None:
    client = get_client("01_minimal")
    r = client.post("/", json=rpc("add", [10, 20]))
    assert r.status_code == 200
    assert r.json()["result"] == 30


# ---------------------------------------------------------------------------
# 02_routing.py
# ---------------------------------------------------------------------------
def test_02_routing_add() -> None:
    client = get_client("02_routing")
    r = client.post("/", json=rpc("math.add", {"a": 3, "b": 4}))
    assert r.status_code == 200
    assert r.json()["result"] == 7


def test_02_routing_multiply_sync() -> None:
    client = get_client("02_routing")
    r = client.post("/", json=rpc("math.multiply", {"x": 3.0, "y": 4.0}))
    assert r.status_code == 200
    assert r.json()["result"] == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# 03_dependencies.py
# ---------------------------------------------------------------------------
def test_03_dependencies_get_user_existing() -> None:
    client = get_client("03_dependencies")
    r = client.post("/", json=rpc("get_user", {"user_id": 1}))
    assert r.status_code == 200
    assert r.json()["result"]["name"] == "Alice"


def test_03_dependencies_get_user_missing() -> None:
    client = get_client("03_dependencies")
    r = client.post("/", json=rpc("get_user", {"user_id": 999}))
    assert r.status_code == 200
    assert r.json()["result"] is None


# ---------------------------------------------------------------------------
# 04_parameters.py
# ---------------------------------------------------------------------------
def test_04_parameters_get_user_explicit_rpc_name() -> None:
    client = get_client("04_parameters")
    r = client.post("/", json=rpc("getUser", {"user_id": 1}))
    assert r.status_code == 200
    assert r.json()["result"]["name"] == "Alice"


def test_04_parameters_original_function_name_not_registered() -> None:
    client = get_client("04_parameters")
    r = client.post("/", json=rpc("get_user_route", {"user_id": 1}))
    assert r.json()["error"]["code"] == -32601


def test_04_parameters_get_user_by_alias() -> None:
    client = get_client("04_parameters")
    r = client.post("/", json=rpc("get_user_by_alias", {"userId": 2}))
    assert r.status_code == 200
    assert r.json()["result"]["name"] == "Bob"


def test_04_parameters_add_with_defaults_all_absent() -> None:
    client = get_client("04_parameters")
    r = client.post("/", json=rpc("add_with_defaults"))
    assert r.status_code == 200
    assert r.json()["result"] == 0


def test_04_parameters_add_with_defaults_partial() -> None:
    client = get_client("04_parameters")
    r = client.post("/", json=rpc("add_with_defaults", {"x": 5}))
    assert r.status_code == 200
    assert r.json()["result"] == 5
