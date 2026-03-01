#!/usr/bin/env -S uv run python
"""02_routing.py: Grouping methods with Routers.

In a larger application, registering all methods directly on `app` gets messy.
`Router` lets you group related methods, similar to FastAPI's `APIRouter` or
Flask's Blueprints. You can optionally mount a router with a prefix.
"""

from wilrise import Router, Wilrise

# Create a router specifically for math operations
math_router = Router()


# Register methods onto the router instead of the app
@math_router.method
def add(a: int, b: int) -> int:
    return a + b


@math_router.method
def multiply(x: float, y: float) -> float:
    """Sync methods like this run automatically in a thread pool."""
    return x * y


# Create the app and include the router
app = Wilrise()

# When we include the router with `prefix="math."`, the actual RPC method names
# become `math.add` and `math.multiply`.
app.include_router(math_router, prefix="math.")

if __name__ == "__main__":
    print("Running routing example at http://127.0.0.1:8000")
    print("Example request (calling math.add):")
    print('  curl -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \\')
    print(
        '    -d \'{"jsonrpc":"2.0", "method":"math.add", '
        '"params":{"a":5, "b":5}, "id":1}\''
    )

    app.run(host="127.0.0.1", port=8000)
