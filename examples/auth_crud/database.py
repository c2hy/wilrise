"""SQLite + SQLAlchemy engine and session dependency."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from .models import AuditLog, Base, RefreshToken, User, UserRole, UserStatus

DB_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("AUTH_CRUD_DB", str(DB_DIR / "auth_crud.db"))
SQLITE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLITE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 15,
    },
    pool_size=20,
    max_overflow=10,
    echo=os.environ.get("SQL_ECHO", "").lower() in ("1", "true"),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db_session(request: Request):
    """Dependency: provide a SQLAlchemy session. Yields session; framework closes
    the generator after the RPC request so this finally runs (session.close()).
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        try:
            session.rollback()
        except Exception:
            pass
        session.close()


def get_user_by_username(session: Session, username: str) -> User | None:
    """Look up user by username."""
    return session.query(User).filter(User.username == username).first()


def get_user_by_id(session: Session, user_id: int) -> User | None:
    """Look up user by id."""
    return session.query(User).filter(User.id == user_id).first()


def get_user_by_email(session: Session, email: str) -> User | None:
    """Look up user by email."""
    return session.query(User).filter(User.email == email).first()


def list_users(
    session: Session,
    skip: int = 0,
    limit: int = 50,
    status: UserStatus | None = None,
    role: UserRole | None = None,
    search: str | None = None,
) -> tuple[list[User], int]:
    """List users with pagination and filters. Returns (users, total_count)."""
    query = session.query(User)
    if status:
        query = query.filter(User.status == status)
    if role:
        query = query.filter(User.role == role)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(search_pattern),
                User.display_name.ilike(search_pattern),
            )
        )
    total = query.count()
    users = query.offset(skip).limit(limit).all()
    return users, total


def create_refresh_token(
    session: Session, user_id: int, token: str, expires_days: int = 7
) -> RefreshToken:
    """Create a new refresh token for a user."""

    expires_at = datetime.now(UTC) + timedelta(days=expires_days)
    rt = RefreshToken(token=token, user_id=user_id, expires_at=expires_at)
    session.add(rt)
    session.commit()
    return rt


def get_refresh_token(session: Session, token: str) -> RefreshToken | None:
    """Get a refresh token by token string."""
    return session.query(RefreshToken).filter(RefreshToken.token == token).first()


def revoke_refresh_token(session: Session, token: str) -> bool:
    """Revoke a refresh token."""
    rt = get_refresh_token(session, token)
    if rt:
        rt.revoked = True
        session.commit()
        return True
    return False


def revoke_all_user_tokens(session: Session, user_id: int) -> int:
    """Revoke all refresh tokens for a user."""
    count = (
        session.query(RefreshToken)
        .filter(RefreshToken.user_id == user_id, RefreshToken.revoked == False)  # noqa: E712
        .update({"revoked": True})
    )
    session.commit()
    return count


def create_audit_log(
    session: Session,
    action: str,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Create an audit log entry."""
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=json.dumps(details) if details else None,
        ip_address=ip_address,
    )
    session.add(log)
    session.commit()
    return log


def list_audit_logs(
    session: Session,
    skip: int = 0,
    limit: int = 50,
    user_id: int | None = None,
    action: str | None = None,
) -> tuple[list[AuditLog], int]:
    """List audit logs with pagination and filters."""
    query = session.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    total = query.count()
    logs = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    return logs, total


def update_last_login(session: Session, user_id: int) -> None:
    """Update user's last login timestamp."""

    user = session.query(User).filter(User.id == user_id).first()
    if user:
        user.last_login_at = datetime.now(UTC)
        session.commit()
