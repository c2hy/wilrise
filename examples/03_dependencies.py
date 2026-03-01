#!/usr/bin/env -S uv run python
"""03_dependencies.py: Dependency Injection.

Like FastAPI, wilrise has a powerful dependency injection system.
You inject dependencies using `Use(...)`.

This example shows how to use a generator dependency to create a mock
database session that is automatically cleaned up (closed) after the request.
"""

from typing import Any

from starlette.requests import Request
from wilrise import Use, Wilrise


class DBSession:
    """A mock database session."""

    def __init__(self) -> None:
        self.connected = True
        self.users = {
            1: {"id": 1, "name": "Alice"},
            2: {"id": 2, "name": "Bob"},
        }

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        return self.users.get(user_id)

    def close(self) -> None:
        """Simulate closing the connection."""
        self.connected = False
        # print("DB session closed.")


def get_db_session(request: Request):
    """Dependency provider.

    Yielding the session lets the framework automatically execute
    the `finally` block to close the session AFTER the RPC method finishes.
    """
    session = DBSession()
    try:
        yield session
    finally:
        session.close()


app = Wilrise()


@app.method
async def get_user(
    user_id: int, db: DBSession = Use(get_db_session)
) -> dict[str, Any] | None:
    """Get a user by ID.

    The client only sends `user_id`. The frameowrk injects the `db` parameter
    by running `get_db_session` for us.
    """
    return await db.get_user(user_id)


if __name__ == "__main__":
    print("Running dependencies example at http://127.0.0.1:8000")
    print("Example request (getting user 1):")
    print('  curl -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \\')
    print(
        '    -d \'{"jsonrpc":"2.0", "method":"get_user", '
        '"params":{"user_id":1}, "id":1}\''
    )

    app.run(host="127.0.0.1", port=8000)
