# Production readiness checklist

Use this checklist before deploying wilrise to production. Details are in the linked docs.

## Configuration

- [ ] **debug** is `False` (or `WILRISE_DEBUG=0`). Never enable debug in production to avoid leaking exception details.
- [ ] **max_batch_size** and **max_request_size** are set per your policy (env: `WILRISE_MAX_BATCH_SIZE`, `WILRISE_MAX_REQUEST_SIZE`). See [configuration.md](configuration.md).
- [ ] **log_requests** / **logger** / **log_level** are configured for your logging pipeline (e.g. `log_level=logging.WARNING` to suppress INFO in production). See [observability.md](observability.md).
- [ ] Secrets (DB URL, JWT secret, etc.) are loaded from environment or a secret manager, not hardcoded. See [configuration.md](configuration.md#敏感信息不入代码).

## Errors and diagnostics

- [ ] **set_exception_mapper** is used to map known third-party exceptions (DB, HTTP client, auth) to stable application or protocol codes, so clients get actionable errors instead of generic -32603. See [errors.md](errors.md).
- [ ] Application errors use **RpcError** with a stable **data.code** (e.g. `auth_failed`) for client handling. See [errors.md](errors.md).
- [ ] Runbook and logging are in place for -32603 / -32602 / -32601; operators know where to look (logger name, request_id, method). See [runbook.md](runbook.md).

## Observability and operations

- [ ] **X-Request-ID** is set at gateway or client for correlation; **RpcContext** / **add_request_logger** are used if you need custom metrics or tracing. See [observability.md](observability.md).
- [ ] Multi-worker / process manager (e.g. gunicorn + uvicorn) and lifespan (**add_startup** / **add_shutdown**) are used for DB pools and other shared resources. See README “Running the server” and [architecture.md](architecture.md).

## Version and upgrades

- [ ] You are on a pinned version; upgrade path and changelog are checked before upgrading. See [versioning.md](versioning.md) and [CHANGELOG.md](../CHANGELOG.md).
