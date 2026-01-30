"""SQLite + SQLAlchemy engine and session dependency."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from .models import Base, User

# SQLite DB file under examples/auth_crud
DB_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("AUTH_CRUD_DB", str(DB_DIR / "auth_crud.db"))
SQLITE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLITE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 15,  # seconds to wait for lock under concurrent access
    },
    pool_size=20,  # allow concurrent requests each with own session/connection
    max_overflow=10,
    echo=os.environ.get("SQL_ECHO", "").lower() in ("1", "true"),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db_session(request: Request) -> Session:
    """Dependency: provide a SQLAlchemy session. Stored in request.state for cleanup."""
    if not hasattr(request.state, "db_session") or request.state.db_session is None:
        request.state.db_session = SessionLocal()
    return request.state.db_session


def close_db_session(request: Request) -> None:
    """Close session after request; rollback uncommitted work (transaction safety)."""
    if hasattr(request.state, "db_session") and request.state.db_session is not None:
        session = request.state.db_session
        try:
            session.rollback()
        except Exception:
            pass
        finally:
            session.close()
            request.state.db_session = None


def get_user_by_username(session: Session, username: str) -> User | None:
    """Look up user by username."""
    return session.query(User).filter(User.username == username).first()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    """Look up user by id."""
    return session.query(User).filter(User.id == user_id).first()


def list_users(session: Session, skip: int = 0, limit: int = 50) -> list[User]:
    """List users with pagination."""
    return session.query(User).offset(skip).limit(limit).all()
