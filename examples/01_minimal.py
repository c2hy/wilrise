#!/usr/bin/env -S uv run python
"""01_minimal.py: The absolute basics of wilrise.

This example shows the simplest possible setup: a single Wilrise app instance
with one method registered. It's the "Hello World" of JSON-RPC.
"""

from wilrise import Wilrise

# Create the application
app = Wilrise()


# Register a method. The function name 'add' becomes the RPC method name.
@app.method
def add(a: int, b: int) -> int:
    """Add two numbers.

    Parameters can be passed positionally (as a JSON array) or
    by keyword (as a JSON object).
    """
    return a + b


if __name__ == "__main__":
    print("Running minimal example at http://127.0.0.1:8000")
    print("Example request:")
    print('  curl -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \\')
    print(
        '    -d \'{"jsonrpc":"2.0", "method":"add", "params":{"a":1, "b":2}, "id":1}\''
    )
    print("\nExpected response:")
    print('  {"jsonrpc":"2.0", "result":3, "id":1}\n')

    # Run the server (uses uvicorn under the hood)
    app.run(host="127.0.0.1", port=8000)
