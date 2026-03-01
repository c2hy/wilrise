#!/usr/bin/env -S uv run python
"""04_parameters.py: Advanced Parameter Options.

For more complex APIs, wilrise allows you to fine-tune how parameters
are received, giving them explicit aliases, defaults, or descriptions.

This example shows how to use `Param` and `Annotated`, and how to
rename the RPC method explicitly without matching the python function name.
"""
# pyright: reportArgumentType=false

from typing import Annotated, Any

from wilrise import Param, Wilrise

app = Wilrise()


# ---------------------------------------------------------------------------
# 1. Using `@app.method("customName")`
# By default, method_name = function name. Use this to override it manually.
# ---------------------------------------------------------------------------
@app.method("getUser")
def get_user_route(user_id: int) -> dict[str, Any]:
    """Client must call "getUser", not "get_user_route"."""
    return {"id": user_id, "name": "Alice"}


# ---------------------------------------------------------------------------
# 2. Using `Param(alias=...)`
# Helpful for matching frontend styles like camelCase without changing Python code.
# ---------------------------------------------------------------------------
@app.method
def get_user_by_alias(
    user_id: Annotated[int, Param(alias="userId", description="User ID")],
) -> dict[str, Any]:
    """Client can pass `"userId": 2` but Python receives `user_id`."""
    return {"id": user_id, "name": "Bob"}


# ---------------------------------------------------------------------------
# 3. Using `Param(default=...)`
# A fallback value when the client omits the parameter.
# ---------------------------------------------------------------------------
@app.method
def add_with_defaults(x: int = Param(0), y: int = Param(0)) -> int:
    """If client omits x or y, they fallback to 0."""
    return x + y


if __name__ == "__main__":
    print("Running advanced parameters example at http://127.0.0.1:8000")
    print("Example request (calling getUser):")
    print('  curl -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \\')
    print('    -d \'{"jsonrpc":"2.0", "method":"getUser", "params":{"user_id":1}, "id":1}\'')

    app.run(host="127.0.0.1", port=8000)
