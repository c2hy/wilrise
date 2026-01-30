# Wilrise example project

Standalone example project showing how to use wilrise in a new project.  
中文说明见 [README.zh-CN.md](README.zh-CN.md).

## Recommended reading order

1. **minimal.py** — Get something running: one method + `app.run()`.
2. **main.py** — Router, dependency injection (`Use`), and optional patterns (Param alias, explicit method name).
3. **auth_crud/** — Full app: SQLAlchemy, JWT auth, CRUD; uses keyed params when methods have both Pydantic and `Use(...)`.

## Files

- **minimal.py** — Minimal: single `add` method and run; good for first-time use.
- **main.py** — Full: Router, `Param` description/alias, `Use` dependency injection, explicit method names.
- **auth_crud/** — Auth + CRUD: SQLAlchemy (SQLite), JWT login, user CRUD.

## Run

**Recommended**: run from the `examples` directory. If you are at the repository root, use `uv run --project examples python examples/<script>` (e.g. `examples/minimal.py`).

**Minimal** (add only):

```bash
cd examples
uv sync
uv run python minimal.py
```

**Full** (math.add, get_user, getUser, get_user_by_alias, etc.):

```bash
cd examples
uv sync
uv run python main.py
```

**Auth + CRUD** (login and user CRUD; run `uv sync` first to install sqlalchemy, pyjwt, bcrypt, etc.):

```bash
cd examples
uv sync
uv run python -m auth_crud.main
```

**From repository root** (same effect):

```bash
uv run --project examples python examples/minimal.py
# or
uv run --project examples python examples/main.py
# or
uv run --project examples python -m auth_crud.main
```

Server is at `http://127.0.0.1:8000`. Example request:

```bash
curl -X POST http://127.0.0.1:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}'
```

## What main.py demonstrates

- **Recommended default**: Method name = function name (e.g. `get_user` → RPC method `get_user`), plain parameters, Router + prefix for grouping.
- **Router + prefix**: `math_router` mounted with prefix `math.` → `math.add`, `math.multiply`, etc.
- **Use**: `db: DBSession = Use(get_db_session)` dependency injection (sync or async provider).
- **Optional when needed**: `Param(alias="userId")` for client naming (e.g. camelCase); `@app.method("getUser")` to fix the RPC method name; `Param(description="...")` for docs.

## Auth + CRUD example

- **Stack**: SQLAlchemy 2 + SQLite, JWT (PyJWT), bcrypt password hashing, Pydantic param validation.
- **RPC methods**:
  - `auth.login` — Login; params `params: { username, password }`; returns `{ access_token, token_type }`.
  - `auth.me` — Current user info (requires header `Authorization: Bearer <token>`).
  - `user.create` — Create user; params `params: { username, password, display_name? }`.
  - `user.list` — List users; params `params: { skip?, limit? }` (optional).
  - `user.get` — Get user by ID (auth required); param `user_id`.
  - `user.update` — Update user (auth required); params `params: { user_id, display_name?, password? }`.
  - `user.delete` — Delete user (auth required); param `user_id`.

When a method has both a Pydantic param and `Use(...)` dependencies, the client must pass the param by name (e.g. under the `params` key). This example uses that **keyed** style; for methods with only one BaseModel param, the main README recommends **whole params** (the entire `params` object as the model).

```bash
# Create user (keyed: param name "params" with value object)
curl -s -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"user.create","params":{"params":{"username":"alice","password":"alice123","display_name":"Alice"}},"id":1}'

# Login (keyed: param name "params")
curl -s -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"auth.login","params":{"params":{"username":"alice","password":"alice123"}},"id":2}'

# Call protected method with token (replace TOKEN with the returned access_token)
curl -s -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" -H "Authorization: Bearer TOKEN" \
  -d '{"jsonrpc":"2.0","method":"auth.me","params":{},"id":3}'
```

Database file defaults to `examples/auth_crud/auth_crud.db`; override with env var `AUTH_CRUD_DB`. This demo uses `debug=True` for easier troubleshooting; in production use `debug=False` or `from_env()` (see main README and [docs/configuration.md](../docs/configuration.md)).

### Concurrency and transaction safety test

`auth_crud/test_concurrent.py` uses a temporary SQLite DB and httpx ASGI transport to run concurrent create/login/list/get/update/delete (20 users in parallel), and asserts no transaction or session leakage (each request gets its own session; uncommitted work is rolled back on close).

```bash
uv sync
uv run python -m auth_crud.test_concurrent
```

Passing the script means concurrent create/login/read/write/delete behave correctly with no cross-request pollution and proper connection-pool and session isolation.

## Other patterns (see main README and docs)

- **Batch requests**: Send a JSON array of JSON-RPC requests in one POST; the server returns an array of responses in the same order. See the main project [README](../README.md#batch-requests).
- **Mounting**: Use `app.as_asgi()` to get the ASGI app and mount under an existing Starlette/FastAPI app (e.g. `app.mount("/rpc", rpc.as_asgi())`). See [Mounting on an existing app](../README.md#mounting-on-an-existing-app).
- **Errors**: Use `RpcError(code, message, data)` for business errors (e.g. auth failure); use `set_exception_mapper` to map third-party exceptions to stable codes. See [docs/errors.md](../docs/errors.md).
