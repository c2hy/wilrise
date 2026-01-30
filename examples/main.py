#!/usr/bin/env -S uv run python
"""Wilrise demo: Router, Use, and optional patterns (Param alias, explicit method name).

Recommended default: method name = function name (e.g. get_user -> RPC "get_user"),
plain parameters, Router + prefix. Use Param(alias=...) and @app.method("name")
only when you need client naming (e.g. camelCase) or a fixed RPC method name.
"""

# pyright: reportArgumentType=none

from typing import Annotated, Any

from starlette.requests import Request
from wilrise import Param, Router, Use, Wilrise

math_router = Router()


@math_router.method
async def add(
    a: Annotated[int, Param(description="first addend")],
    b: Annotated[int, Param(description="second addend")],
) -> int:
    """Add two numbers (registered on math_router)."""
    return a + b


@math_router.method
async def add_with_defaults(x: int = Param(0), y: int = Param(0)) -> int:
    """Add with default values (registered on math_router)."""
    return x + y


@math_router.method
def multiply(x: float, y: float) -> float:
    """Sync multiplication (registered on math_router)."""
    return x * y


# ---------- Create app and mount router ----------
app = Wilrise()
app.include_router(math_router, prefix="math.")


# ---------- Mock DB Session ----------
class DBSession:
    """Mock database session."""

    def __init__(self) -> None:
        self._data: dict[int, dict[str, Any]] = {
            1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
            2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
        }

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        return self._data.get(user_id)

    def get_user_sync(self, user_id: int) -> dict[str, Any] | None:
        return self._data.get(user_id)


async def get_db_session(request: Request) -> DBSession:
    """Dependency: provide DB session. Async; can access request."""
    # In real apps: get from pool, request.state, etc.
    return DBSession()


# ---------- Methods registered directly on app ----------
# Recommended default: method name = function name, plain params (see get_user below).
# Optional: Param(alias=...) and @app.method("name") when client/fixed RPC name needed.


@app.method
async def get_user(
    user_id: int, db: DBSession = Use(get_db_session)
) -> dict[str, Any] | None:
    """Recommended: RPC method name is "get_user"; plain params + Use for DI."""
    return await db.get_user(user_id)


@app.method
async def get_user_by_alias(
    user_id: Annotated[int, Param(alias="userId", description="user ID")],
    db: DBSession = Use(get_db_session),
) -> dict[str, Any] | None:
    """Optional: Param(alias="userId") so client can send "userId" not "user_id"."""
    return await db.get_user(user_id)


@app.method("getUser")
async def get_user_route(
    user_id: int, db: DBSession = Use(get_db_session)
) -> dict[str, Any] | None:
    """Optional: RPC method "getUser" instead of function name get_user_route."""
    return await db.get_user(user_id)


# ---------- Run ----------
if __name__ == "__main__":
    print("JSON-RPC server: http://127.0.0.1:8000")
    print("Example requests:")
    print("  math.add / math.multiply / math.add_with_defaults  (Router + prefix)")
    print("  get_user / getUser / get_user_by_alias             (direct @app.method)")
    print('  curl -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \\')
    print(
        '    -d \'{"jsonrpc":"2.0","method":"math.add","params":{"a":1,"b":2},"id":1}\''
    )
    # app.run() uses uvicorn with access_log=False so only JSON-RPC style logs are shown
    app.run(host="127.0.0.1", port=8000)
