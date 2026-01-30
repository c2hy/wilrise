#!/usr/bin/env -S uv run python
"""Minimal real DB example: SQLite + SQLAlchemy, get_user / list_users / create_user."""

# pyright: reportArgumentType=none

from typing import Any

from sqlalchemy.orm import Session
from wilrise import Use, Wilrise

from .database import get_db_session, init_db
from .models import User

app = Wilrise(debug=True)
init_db()


@app.method
def get_user(user_id: int, db: Session = Use(get_db_session)) -> dict[str, Any] | None:
    """Get user by id."""
    user = db.get(User, user_id)
    return user.to_dict() if user else None


@app.method
def list_users(db: Session = Use(get_db_session)) -> list[dict[str, Any]]:
    """List all users."""
    users = db.query(User).all()
    result: list[dict[str, Any]] = [u.to_dict() for u in users]
    return result


@app.method
def create_user(
    name: str,
    email: str,
    db: Session = Use(get_db_session),
) -> dict[str, Any]:
    """Create a user."""
    user = User(name=name, email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    out: dict[str, Any] = user.to_dict()
    return out


if __name__ == "__main__":
    print("JSON-RPC + real DB: http://127.0.0.1:8000")
    print("Methods: get_user, list_users, create_user")
    app.run(host="127.0.0.1", port=8000)
