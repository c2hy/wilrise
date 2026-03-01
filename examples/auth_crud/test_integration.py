"""Integration tests for auth_crud: login, user CRUD over JSON-RPC.

Tests cover both happy-path flows and error-path flows (RpcError propagation),
making this file a feature test for wilrise's error handling and DI in a real app.
"""

import os
import tempfile
from typing import Any

from starlette.testclient import TestClient

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ.setdefault("AUTH_CRUD_DB", _db_path)

from auth_crud.main import app  # noqa: E402

client = TestClient(app.as_asgi())


def rpc(
    method: str,
    params: dict[str, Any] | list[Any] | None = None,
    id: int = 1,
) -> dict[str, Any]:
    req: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        req["params"] = params
    return req


def create_user(
    username: str,
    password: str = "pass123!",
    display: str = "",
    email: str | None = None,
) -> dict[str, Any]:
    """Helper: create a user and return the result dict."""
    params = {
        "username": username,
        "password": password,
        "display_name": display or username,
    }
    if email:
        params["email"] = email
    r = client.post(
        "/",
        json=rpc("user.create", {"params": params}),
    )
    assert r.status_code == 200
    data = r.json()
    assert "result" in data, f"create_user failed: {data}"
    return data["result"]


def login(username: str, password: str = "pass123!") -> dict[str, Any]:
    """Helper: login and return full result with tokens."""
    r = client.post(
        "/",
        json=rpc(
            "auth.login",
            {"params": {"username": username, "password": password}},
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert "result" in data, f"login failed: {data}"
    return data["result"]


def test_login_invalid_returns_error() -> None:
    """Invalid login → -32001 (RpcError propagated correctly)."""
    r = client.post(
        "/",
        json=rpc(
            "auth.login",
            {"params": {"username": "nobody", "password": "x"}},
        ),
    )
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32001


def test_login_returns_tokens() -> None:
    """Valid login → access_token and refresh_token present in result."""
    create_user("logintest")
    result = login("logintest")
    assert isinstance(result["access_token"], str) and len(result["access_token"]) > 10
    assert isinstance(result["refresh_token"], str) and len(result["refresh_token"]) > 10


def test_refresh_token_flow() -> None:
    """Refresh token can be used to get new access token."""
    create_user("refreshtest")
    result = login("refreshtest")
    refresh = result["refresh_token"]

    r = client.post(
        "/",
        json=rpc("auth.refresh", {"params": {"refresh_token": refresh}}),
    )
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    assert "access_token" in data["result"]
    assert "refresh_token" in data["result"]
    assert data["result"]["refresh_token"] != refresh


def test_refresh_token_revoked_after_use() -> None:
    """Used refresh token cannot be reused."""
    create_user("refreshtest2")
    result = login("refreshtest2")
    refresh = result["refresh_token"]

    r1 = client.post(
        "/",
        json=rpc("auth.refresh", {"params": {"refresh_token": refresh}}),
    )
    assert r1.status_code == 200
    assert "result" in r1.json()

    r2 = client.post(
        "/",
        json=rpc("auth.refresh", {"params": {"refresh_token": refresh}}),
    )
    assert r2.status_code == 200
    data = r2.json()
    assert "error" in data
    assert data["error"]["code"] == -32001


def test_create_user_and_list() -> None:
    """Create user via user.create, then user.list includes it."""
    create_user("listuser")

    r = client.post(
        "/",
        json=rpc("user.list", {"params": {"skip": 0, "limit": 100}}),
    )
    assert r.status_code == 200
    result = r.json()["result"]
    usernames = [u["username"] for u in result["users"]]
    assert "listuser" in usernames


def test_user_list_with_filters() -> None:
    """User list supports status and role filters."""
    create_user("filteruser1")
    create_user("filteruser2")

    r = client.post(
        "/",
        json=rpc("user.list", {"params": {"skip": 0, "limit": 100, "status": "active"}}),
    )
    assert r.status_code == 200
    result = r.json()["result"]
    assert "users" in result
    assert "pagination" in result
    assert "total" in result["pagination"]


def test_user_list_with_search() -> None:
    """User list supports search."""
    create_user("searchuser1", display="Alice")
    create_user("searchuser2", display="Bob")

    r = client.post(
        "/",
        json=rpc("user.list", {"params": {"skip": 0, "limit": 100, "search": "Alice"}}),
    )
    assert r.status_code == 200
    result = r.json()["result"]
    assert len(result["users"]) >= 1
    assert any("Alice" in u.get("display_name", "") for u in result["users"])


def test_create_duplicate_username_returns_rpc_error() -> None:
    """Creating a user with an already-taken username → -32002 (RpcError)."""
    create_user("dupuser")
    r = client.post(
        "/",
        json=rpc(
            "user.create",
            {
                "params": {
                    "username": "dupuser",
                    "password": "pass123!",
                    "display_name": "",
                }
            },
        ),
    )
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32002


def test_login_then_me() -> None:
    """Login returns token; auth.me with valid token returns the correct user."""
    create_user("meuser", display="Me")
    result = login("meuser")
    token = result["access_token"]

    r = client.post(
        "/",
        json=rpc("auth.me", {}),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    me = r.json()["result"]
    assert me["username"] == "meuser"


def test_me_without_token_returns_rpc_error() -> None:
    """auth.me without Authorization header → -32001 (unauthorized)."""
    r = client.post("/", json=rpc("auth.me", {}))
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32001


def test_me_with_invalid_token_returns_rpc_error() -> None:
    """auth.me with garbage token → -32001 (JWT decode failure → RpcError)."""
    r = client.post(
        "/",
        json=rpc("auth.me", {}),
        headers={"Authorization": "Bearer not.a.valid.token"},
    )
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32001


def test_user_get_requires_auth() -> None:
    """user.get without token → -32001 from get_current_user Use provider."""
    user = create_user("getauthuser")
    r = client.post("/", json=rpc("user.get", {"params": {"user_id": user["id"]}}))
    assert r.json()["error"]["code"] == -32001


def test_user_full_crud_flow() -> None:
    """Full CRUD: create → get → update → delete."""
    user = create_user("cruduser", display="Original")
    result = login("cruduser")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post("/", json=rpc("user.get", {"params": {"user_id": user["id"]}}), headers=auth)
    assert r.json()["result"]["display_name"] == "Original"

    r = client.post(
        "/",
        json=rpc(
            "user.update",
            {"params": {"user_id": user["id"], "display_name": "Updated"}},
        ),
        headers=auth,
    )
    assert r.json()["result"]["display_name"] == "Updated"

    r = client.post("/", json=rpc("user.get", {"params": {"user_id": user["id"]}}), headers=auth)
    assert r.json()["result"]["display_name"] == "Updated"

    r = client.post("/", json=rpc("user.delete", {"params": {"user_id": user["id"]}}), headers=auth)
    assert r.json()["result"] is True

    r = client.post("/", json=rpc("user.list", {"params": {"skip": 0, "limit": 100}}))
    usernames = [u["username"] for u in r.json()["result"]["users"]]
    assert "cruduser" not in usernames


def test_change_password() -> None:
    """User can change their password."""
    create_user("pwuser", password="oldpass123")
    result = login("pwuser", password="oldpass123")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc(
            "user.changePassword",
            {
                "params": {
                    "current_password": "oldpass123",
                    "new_password": "newpass456",
                }
            },
        ),
        headers=auth,
    )
    assert r.status_code == 200
    assert r.json()["result"]["success"] is True

    r = client.post(
        "/",
        json=rpc(
            "auth.login",
            {"params": {"username": "pwuser", "password": "newpass456"}},
        ),
    )
    assert "result" in r.json()


def test_change_password_wrong_current() -> None:
    """Change password with wrong current password fails."""
    create_user("pwuser2", password="correct123")
    result = login("pwuser2", password="correct123")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc(
            "user.changePassword",
            {
                "params": {
                    "current_password": "wrongpassword",
                    "new_password": "newpass456",
                }
            },
        ),
        headers=auth,
    )
    assert "error" in r.json()
    assert r.json()["error"]["code"] == -32001


def test_update_profile() -> None:
    """User can update their profile."""
    create_user("profileuser")
    result = login("profileuser")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc(
            "user.updateProfile",
            {"params": {"display_name": "New Name", "bio": "Hello world"}},
        ),
        headers=auth,
    )
    assert r.status_code == 200
    assert r.json()["result"]["display_name"] == "New Name"
    assert r.json()["result"]["bio"] == "Hello world"


def test_logout() -> None:
    """Logout revokes refresh token."""
    create_user("logoutuser")
    result = login("logoutuser")
    token = result["access_token"]
    refresh = result["refresh_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc("auth.logout", {"params": {"refresh_token": refresh}}),
        headers=auth,
    )
    assert r.status_code == 200
    assert r.json()["result"]["success"] is True

    r = client.post(
        "/",
        json=rpc("auth.refresh", {"params": {"refresh_token": refresh}}),
    )
    assert "error" in r.json()


def test_admin_set_user_status() -> None:
    """Admin can set user status."""
    create_user("admin1")
    from auth_crud.database import SessionLocal
    from auth_crud.models import User, UserRole

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == "admin1").first()
        assert user is not None
        user.role = UserRole.ADMIN
        session.commit()
    finally:
        session.close()

    target = create_user("targetuser")
    result = login("admin1")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc(
            "admin.user.setStatus",
            {"params": {"user_id": target["id"], "status": "suspended"}},
        ),
        headers=auth,
    )
    assert r.status_code == 200
    assert r.json()["result"]["status"] == "suspended"


def test_admin_set_user_role() -> None:
    """Admin can set user role."""
    create_user("admin2")
    from auth_crud.database import SessionLocal
    from auth_crud.models import User, UserRole

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == "admin2").first()
        assert user is not None
        user.role = UserRole.ADMIN
        session.commit()
    finally:
        session.close()

    target = create_user("targetuser2")
    result = login("admin2")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc(
            "admin.user.setRole",
            {"params": {"user_id": target["id"], "role": "admin"}},
        ),
        headers=auth,
    )
    assert r.status_code == 200
    assert r.json()["result"]["role"] == "admin"


def test_non_admin_cannot_access_admin_methods() -> None:
    """Non-admin users cannot access admin methods."""
    create_user("normaluser")
    target = create_user("targetuser3")
    result = login("normaluser")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc(
            "admin.user.setStatus",
            {"params": {"user_id": target["id"], "status": "suspended"}},
        ),
        headers=auth,
    )
    assert "error" in r.json()
    assert r.json()["error"]["code"] == -32003


def test_admin_list_audit_logs() -> None:
    """Admin can list audit logs."""
    create_user("admin3")
    from auth_crud.database import SessionLocal
    from auth_crud.models import User, UserRole

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == "admin3").first()
        assert user is not None
        user.role = UserRole.ADMIN
        session.commit()
    finally:
        session.close()

    result = login("admin3")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc("admin.auditLogs", {"params": {"skip": 0, "limit": 10}}),
        headers=auth,
    )
    assert r.status_code == 200
    result = r.json()["result"]
    assert "logs" in result
    assert "pagination" in result


def test_batch_request() -> None:
    """Batch requests work correctly."""
    create_user("batchuser1")
    create_user("batchuser2")

    r = client.post(
        "/",
        json=[
            rpc("user.list", {"params": {"skip": 0, "limit": 10}}),
            rpc("auth.me", {}),
        ],
    )
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 2
    assert "result" in results[0]
    assert "error" in results[1]


def test_notification_no_response() -> None:
    """Notifications (no id) return no response."""
    r = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "method": "user.list",
            "params": {"skip": 0, "limit": 10},
        },
    )
    assert r.status_code == 204


def test_user_create_pydantic_validation_failure() -> None:
    """Password too short → Pydantic -32602 Invalid params with validation_errors."""
    r = client.post(
        "/",
        json=rpc(
            "user.create",
            {"params": {"username": "badpw", "password": "x", "display_name": ""}},
        ),
    )
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32602
    assert "validation_errors" in data["error"]["data"]


def test_user_create_with_email() -> None:
    """User can be created with email."""
    r = client.post(
        "/",
        json=rpc(
            "user.create",
            {
                "params": {
                    "username": "emailuser",
                    "password": "pass123!",
                    "display_name": "Email User",
                    "email": "test@example.com",
                }
            },
        ),
    )
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["email"] == "test@example.com"


def test_user_get_returns_public_for_non_admin() -> None:
    """Non-admin users get public profile when viewing other users."""
    create_user("viewer")
    target = create_user("viewtarget", display="Target User")

    result = login("viewer")
    token = result["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/",
        json=rpc("user.get", {"params": {"user_id": target["id"]}}),
        headers=auth,
    )
    assert r.status_code == 200
    user = r.json()["result"]
    assert "username" in user
    assert "display_name" in user
    assert "email" not in user or user.get("email") is None
