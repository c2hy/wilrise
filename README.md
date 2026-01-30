# wilrise

Wilrise is a **server-side JSON-RPC framework** built on [Starlette](https://www.starlette.io/). It targets teams that want RPC semantics (method-oriented API, batch support) while staying inside the ASGI ecosystem—e.g. mount under an existing Starlette/FastAPI app, reuse middleware, and use async throughout. Simple to get started; see [docs/](docs/) for production topics (errors, configuration, observability, versioning, runbook, architecture).

This document assumes you are already familiar with **JSON-RPC 2.0** (request/response format, method, params, id, error codes). The framework implements the server side only; use any JSON-RPC 2.0–compliant client to call your methods.

## Install

```bash
# With uv (recommended)
uv add wilrise

# Or pip
pip install wilrise
```

After installing, use `from wilrise import Wilrise` in your code. For parameter validation (clear -32602 instead of -32603 on type errors), install the optional extra: `uv add "wilrise[pydantic]"` or `pip install "wilrise[pydantic]"`.

## Quick start

**1. Write a minimal service** (e.g. `main.py`):

```python
from wilrise import Wilrise

app = Wilrise()

@app.method
def add(a: int, b: int) -> int:
    return a + b

# Recommended: app.run() uses uvicorn with access_log=False and built-in JSON-RPC style logs
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
```

**2. Run the server** (from the directory that contains `main.py`):

```bash
uv run python main.py
```

You’ll see JSON-RPC style logs (e.g. `JSON-RPC add → 200 in 12.50ms`) instead of generic "POST / 200" lines. To use another ASGI server or mount under an existing app, use `app.as_asgi()` (see [Mounting on an existing app](#mounting-on-an-existing-app) below).

If you use the repo’s **examples**, from project root:

```bash
uv run --project examples python examples/minimal.py
```

**3. Send a request** (single call):

```bash
curl -X POST http://127.0.0.1:8000/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}'
```

Example response: `{"jsonrpc":"2.0","result":3,"id":1}`.

- Request body must be JSON with `"jsonrpc":"2.0"`, `"method"` (method name), optional `"params"` (object or array), and optional `"id"` (omit for notifications; no response body).

### Batch requests

Send an array of JSON-RPC requests in one POST; the response is an array of responses **in the same order**. Notifications (no `id`) do not get an entry in the response array. If all requests are notifications, the server returns 204 No Content. One failed request does not fail the whole batch; each request gets its own success or error response.

## Advanced: dependency injection & routers

Use **Router** and `include_router(router, prefix="...")` to group methods by module (e.g. `math.add`, `user.get`). See `examples/main.py` for a full pattern.

```python
from wilrise import Router, Use, Wilrise
from starlette.requests import Request

app = Wilrise()

# Dependency provider (e.g. from request, connection pool)
async def get_db_session(request: Request):
    return DBSession()  # e.g. from pool, request.state, etc.

@app.method
async def add(a: int, b: int) -> int:
    return a + b

@app.method
async def get_user(user_id: int, db: DBSession = Use(get_db_session)) -> dict | None:
    return await db.get_user(user_id)  # db is injected by Use

# If Use(provider) raises, the request returns -32603 (Internal error); treat as dependency failure.
# Standalone: app.run(); mounting: app.as_asgi()
```

## Prerequisites

- Built on **Starlette**; if you know ASGI or FastAPI, you’ll feel at home (`@app.method` ≈ route, `Use` ≈ dependency injection — similar to FastAPI’s `Depends`).
- **Without** the optional Pydantic extra, parameter types are **not** validated; wrong types (e.g. passing a string where an int is expected) lead to **Internal error** (-32603) or unexpected behavior. To get clear **Invalid params** (-32602) on type errors, install: `uv add "wilrise[pydantic]"` (see [Pydantic (optional)](#pydantic-optional) below).

## Configuration

`Wilrise` accepts these init options:

- **debug** (default `False`): When `True`, error responses include full exception info. **Keep `False` in production** to avoid leaking sensitive data.
- **max_batch_size** (default `50`): Max number of requests in a batch; excess returns -32600.
- **max_request_size** (default `1024*1024`, 1MB): Max request body size in bytes; **only checked when `Content-Length` is present**—requests without this header are not size-limited by the framework. Excess returns 413. For strict limits regardless of headers (e.g. production), use a reverse proxy or custom middleware.
- **log_requests** (default `True`): When `True`, each request is logged in JSON-RPC style: method name(s), HTTP status, and duration (e.g. `JSON-RPC math.add → 200 in 12.50ms`; for batches, `JSON-RPC batch(n) [method1, ...] → 200 in 45ms`).
- **logger** (default `None`): Logger to use for request and error logs. If `None`, uses `logging.getLogger("wilrise.core")`. Pass a custom logger (e.g. `logging.getLogger("app.rpc")`) to control level and handlers per app.
- **log_level** (default `None`): If set, call `logger.setLevel(log_level)` so only messages at or above this level are emitted (e.g. `logging.WARNING` in production to suppress INFO success logs but keep ERROR).

You can pass options in code or load them from environment variables (e.g. `WILRISE_DEBUG`, `WILRISE_MAX_BATCH_SIZE`, `WILRISE_LOG_LEVEL`). See [docs/configuration.md](docs/configuration.md) for env var names, default/dev/production presets, and the optional `from_env()` helper.

```python
# Production (recommend from env in deployment)
from wilrise import Wilrise, from_env
app = Wilrise(**from_env())

# Or explicitly
app = Wilrise(debug=False, max_batch_size=50, max_request_size=1024 * 1024)

# Development: enable debug for troubleshooting
app = Wilrise(debug=True)
```

### Running the server

- **Recommended**: `app.run(host="127.0.0.1", port=8000)` — runs uvicorn with `access_log=False` so only JSON-RPC style logs (method, status, duration) are printed. Optional args: `app.run(host="0.0.0.0", port=8000, access_log=True, **uvicorn_kwargs)`.
- **Alternative**: `uvicorn.run(app.as_asgi(), host="127.0.0.1", port=8000, access_log=False)` if you need to pass other uvicorn options.
- **Multi-worker**: The app is stateless; use multiple uvicorn workers (e.g. `uvicorn ... --workers 4`). Shared resources (DB pool, Redis) should be initialized in **startup** and closed in **shutdown** so each worker has its own connections. **Production**: run behind a process manager (e.g. gunicorn + uvicorn worker), set `debug=False`, and configure via environment variables.
- **Mounting**: Use `app.as_asgi()` to get the Starlette app and mount it under another application (see [Mounting on an existing app](#mounting-on-an-existing-app) below).

## Middleware

Add Starlette middleware (CORS, auth, logging, etc.) with `add_middleware`:

```python
from starlette.middleware.base import BaseHTTPMiddleware

app = Wilrise()

class CustomMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Before request...
        response = await call_next(request)
        # After response...
        return response

app.add_middleware(CustomMiddleware)
```

## Example project

`examples/` is a demo project with the same layout as using wilrise in a new project. Recommended order: **minimal.py** → **main.py** → **auth_crud/** (see [examples/README.md](examples/README.md)).

```text
examples/
├── pyproject.toml   # depends on wilrise
├── minimal.py       # Minimal: single add method + run
├── main.py          # Full: Router, Param, Use, aliases, etc.
└── auth_crud/      # Full app: SQLAlchemy, JWT auth, CRUD (whole-params style)
```

- **Minimal** (only `add`):

  ```bash
  cd examples && uv sync && uv run python minimal.py
  ```

- **Full** (Router, DI, Param aliases, etc.):

  ```bash
  cd examples && uv sync && uv run python main.py
  ```

- **Auth + CRUD** (login, user CRUD; run `uv sync` first):

  ```bash
  cd examples && uv sync && uv run python -m auth_crud.main
  ```

From repo root:

```bash
uv run --project examples python examples/minimal.py
# or
uv run --project examples python examples/main.py
# or
uv run --project examples python -m auth_crud.main
```

> For local development, `pyproject.toml` points at the local wilrise via `[tool.uv.sources]`. Remove that section when installing from PyPI.

## Pydantic (optional)

**Without** the `pydantic` extra, parameter types (e.g. `int`, `str`) are **not** validated; wrong types may lead to `-32603` or unexpected behavior. For declarative validation, install:

```bash
uv add "wilrise[pydantic]"
# or pip install "wilrise[pydantic]"
```

- **Single param of type BaseModel**: Two valid ways to call; **recommended** is **whole params** (the entire `params` object is the model). Clients and server should agree on one style per method.
  - **Whole params** (recommended): `"params": {"a": 1, "b": 2}` → validated as `AddParams`.
  - **Keyed**: `"params": {"params": {"a": 1, "b": 2}}` → only the value for the key `params` is validated.
- **Multiple params**: Any param annotated with a `BaseModel` has its JSON validated and deserialized to that model.
- On validation failure, `-32602` (Invalid params) is returned; all `-32602` responses use `error.data.validation_errors` (list of `{loc, msg, type, ...}`) for consistent client handling.
- **Return values** must be JSON-serializable; otherwise the server returns `-32603`.

Example:

```python
from pydantic import BaseModel
from wilrise import Wilrise

app = Wilrise()

class AddParams(BaseModel):
    a: int
    b: int

@app.method
def add(params: AddParams) -> int:
    return params.a + params.b
```

Both requests below return `result: 3`. Use the recommended whole-params style and keep it consistent with your client.

```bash
# Whole params object (recommended for single BaseModel param)
curl -X POST http://127.0.0.1:8000/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}'

# Keyed: params.params
curl -X POST http://127.0.0.1:8000/ -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"params":{"a":1,"b":2}},"id":1}'
```

## Development and code style

Install dev dependencies first:

```bash
uv sync --group dev
```

**Formatting & linting** — [Ruff](https://docs.astral.sh/ruff/):

- **Format**: `uv run ruff format .`
- **Lint**: `uv run ruff check .`
- **Both**: `uv run ruff format . && uv run ruff check .`

**Type checking** — [Pyright](https://microsoft.github.io/pyright/) (strict mode):

- **Type check**: `uv run pyright`

Configuration in `[tool.ruff]` and `[tool.pyright]` in `pyproject.toml`. Run the above before committing to keep style and types consistent. For full setup, tests, and how to contribute, see [CONTRIBUTING](CONTRIBUTING.md) ([中文](CONTRIBUTING.zh-CN.md)).

## Contributing

Bug reports, feature ideas, and pull requests are welcome. See [CONTRIBUTING](CONTRIBUTING.md) for development setup, code style, and PR guidelines ([中文](CONTRIBUTING.zh-CN.md)).

## Error codes (JSON-RPC 2.0)

- **-32700** Parse error — request body is not valid JSON.
- **-32600** Invalid Request — missing `jsonrpc`/`method`, method not string, params not object/array, body too large, batch over limit, etc.
- **-32601** Method not found — called method is not registered.
- **-32602** Invalid params — missing required param, Pydantic validation failed, etc. All `-32602` responses use `error.data.validation_errors` (list of `{loc, msg, type}`) for consistent client handling.
- **-32603** Internal error — method or dependency (Use) raised an exception, or result not JSON-serializable (details hidden in production). In production, use `set_exception_mapper` to map known exceptions (e.g. DB, auth) to specific codes so clients get actionable errors instead of a generic "Internal error".

For **application-level errors** (-32099..-32000), raise `RpcError(code, message, data=...)` in your method or Use provider; use `data` (e.g. `data={"code": "auth_failed"}`) for stable client handling. For **third-party exceptions** (DB, HTTP client), use `set_exception_mapper(mapper)` to map them to a protocol or application code instead of exposing -32603. See [docs/errors.md](docs/errors.md) for error layering, retriable guidance, and ExceptionMapper vs RpcError order.

## Mounting on an existing app

Mount the JSON-RPC app on a path (e.g. `/rpc`) in Starlette or FastAPI:

```python
from starlette.applications import Starlette
from starlette.routing import Mount

from wilrise import Wilrise

rpc = Wilrise()

@rpc.method
def add(a: int, b: int) -> int:
    return a + b

# Mount on /rpc; requests go to http://host/rpc
app = Starlette(routes=[Mount("/rpc", app=rpc.as_asgi())])
# Then: curl -X POST http://127.0.0.1:8000/rpc -H "Content-Type: application/json" \
#   -d '{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}'
```

With FastAPI: `app.mount("/rpc", rpc.as_asgi())`.

## Param and Use

- **Param(description=..., alias=...)**: `description` is metadata only (e.g. for your own docs or OpenRPC); `alias` lets the client send a different key (e.g. `userId` instead of `user_id`).
- **Use(provider)**: Injects the provider’s return value. If the provider raises, the request returns `-32603` (Internal error); treat it as dependency failure (e.g. DB or auth).

## Observability

- **Logging**: Configure the `wilrise` logger (e.g. `logging.getLogger("wilrise").setLevel(logging.INFO)`) to control level and handlers. The framework logs each request with `extra` (request_id, rpc_methods, status_code, duration_ms). For JSON/structured logs or custom sinks, use `add_request_logger(logger_fn)`. To use [Loguru](https://github.com/Delgan/loguru) as the log backend, see the tutorial in [docs/observability.md](docs/observability.md#教程使用-loguru-作为日志后端).
- **Request ID**: Set the `X-Request-ID` header at the gateway or client; it is available as `RpcContext.http_request_id` and in log extras for correlation.
- **Tracing / metrics**: [docs/observability.md](docs/observability.md) describes optional OpenTelemetry and metrics patterns via `add_request_logger` or middleware.

## Version and compatibility

- **Versioning**: [Semantic Versioning](https://semver.org/) (MAJOR.MINOR.PATCH). Current status: **Beta (0.1.x)**; before 1.0 we may make breaking changes; from 1.0 we keep backward compatibility within each MAJOR. See [docs/versioning.md](docs/versioning.md) and [CHANGELOG.md](CHANGELOG.md).
- **Upgrades**: When we release a new MAJOR or significant MINOR, we add upgrade notes under `docs/` (e.g. `docs/upgrade-1.0.md`).

## FAQ

- **How can clients discover available methods?**  
  JSON-RPC 2.0 does not require a schema; this framework does not ship OpenAPI or built-in method discovery. You can add your own RPC method that returns the list of method names (and param docs if you maintain them), or serve OpenRPC / self-describing docs.

- **Why Python 3.12+?**  
  The project targets a single modern version for type hints, performance, and maintainability; support for older Python versions is not planned for now.

## Project structure

- **wilrise** — Core implementation; optional `from_env` in `wilrise.config`.
- **examples/** — Demo project (minimal + full example).
- **docs/** — Production topics: [errors](docs/errors.md), [configuration](docs/configuration.md), [observability](docs/observability.md), [versioning](docs/versioning.md), [runbook](docs/runbook.md), [architecture](docs/architecture.md), [production checklist](docs/PRODUCTION_READINESS_CHECKLIST.md).

---

中文说明见 [README.zh-CN.md](README.zh-CN.md)。
