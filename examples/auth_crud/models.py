"""SQLAlchemy models for auth_crud example."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all models."""


class User(Base):
    """User model: username, hashed password, display name, created_at."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def to_dict(self) -> dict[str, Any]:
        """Export to JSON-serializable dict (no password)."""
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
