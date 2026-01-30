"""SQLite + SQLAlchemy session dependency."""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from .models import Base

DB_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("DB_EXAMPLE_PATH", str(DB_DIR / "example.db"))
SQLITE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create tables."""
    Base.metadata.create_all(bind=engine)


def get_db_session(request: Request):
    """Dependency: yield session; framework closes generator after RPC."""
    session = SessionLocal()
    try:
        yield session
    finally:
        try:
            session.rollback()
        except Exception:
            pass
        session.close()
