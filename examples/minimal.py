#!/usr/bin/env -S uv run python
"""Minimal example: register only the add method and run the server.

Good for first-time use.
"""

from wilrise import Wilrise

app = Wilrise()


@app.method
def add(a: int, b: int) -> int:
    """Add two numbers. RPC method name is add; params as {"a": 1, "b": 2} or [1, 2]."""
    return a + b


if __name__ == "__main__":
    print("JSON-RPC server: http://127.0.0.1:8000")
    print("Example request:")
    print('  curl -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \\')
    print('    -d \'{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}\'')
    app.run(host="127.0.0.1", port=8000)
