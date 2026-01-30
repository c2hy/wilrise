"""SQLAlchemy model for db example."""

from typing import Any

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base."""


class User(Base):
    """User: id, name, email."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(nullable=False)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict."""
        return {"id": self.id, "name": self.name, "email": self.email}
