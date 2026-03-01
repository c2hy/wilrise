# wilrise

Wilrise is a **server-side JSON-RPC framework** built on [Starlette](https://www.starlette.io/).

It targets teams that want RPC semantics (method-oriented API, batch support) while staying inside the ASGI ecosystem. It supports mounting under an existing Starlette/FastAPI app, reusing middleware, dependency injection, and Pydantic validation.

This document assumes you are already familiar with **JSON-RPC 2.0**. The framework implements the server side only; use any JSON-RPC 2.0–compliant client to call your methods.

## Install

```bash
# With uv (recommended)
uv add wilrise

# Or pip
pip install wilrise
```

For Pydantic validation and clear `Invalid params` (-32602) error codes on type mismatches, install the optional extra: `uv add "wilrise[pydantic]"`.

## Quick start

**1. Write a minimal service** (e.g. `main.py`):

```python
from wilrise import Wilrise

app = Wilrise()

@app.method
def add(a: int, b: int) -> int:
    return a + b

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
```

**2. Run the server**:

```bash
uv run python main.py
```

**3. Send a request**:

```bash
curl -X POST http://127.0.0.1:8000/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0", "method":"add", "params":{"a":1, "b":2}, "id":1}'
```

Response: `{"jsonrpc":"2.0","result":3,"id":1}`

## Learning by Examples

To learn the framework quickly, we highly recommend checking out the `examples/` directory. It contains step-by-step runnable tutorials:

1. **[01_minimal.py](examples/01_minimal.py)** — The absolute basics.
2. **[02_routing.py](examples/02_routing.py)** — Grouping methods with `Router` and prefixes.
3. **[03_dependencies.py](examples/03_dependencies.py)** — Dependency injection (`Use`).
4. **[04_parameters.py](examples/04_parameters.py)** — Advanced parameters (`Param` alias/default).
5. **[auth_crud/](examples/auth_crud/)** — A full production-like app with SQLAlchemy, JWT auth, and CRUD.

Run the examples from the `examples` folder:

```bash
cd examples
uv sync
uv run python 01_minimal.py
```

See [examples/README.md](examples/README.md) for more details.

## Documentation Index

For advanced topics, production readiness, and deep-dives, see the specific guides in the `docs/` folder:

- 📖 **Architecture & Lifecycle**: How a request is processed from HTTP to JSON-RPC and back. [Read architecture.md](docs/architecture.md)
- ⚙️ **Configuration**: Environment variables, payload limits, and debugging. [Read configuration.md](docs/configuration.md)
- 🚨 **Errors & Exceptions**: Protocol vs App errors, `RpcError`, and mapping third-party exceptions. [Read errors.md](docs/errors.md)
- 📊 **Observability**: Logging requests, Trace IDs, and integrating with OpenTelemetry / Loguru. [Read observability.md](docs/observability.md)
- 🛠 **Troubleshooting & Runbook**: Handling common issues like 413, -32600, or -32603. [Read runbook.md](docs/runbook.md)
- 🔄 **FastAPI Migration**: Coming from FastAPI? See the exact feature mapping. [Read migration-from-fastapi.md](docs/migration-from-fastapi.md)
- 🚀 **Production Checklist**: What to check before going live. [Read PRODUCTION_READINESS_CHECKLIST.md](docs/PRODUCTION_READINESS_CHECKLIST.md)

## Development and Contributing

Bugs and feature requests are welcome. See [CONTRIBUTING](CONTRIBUTING.md) ([中文](CONTRIBUTING.zh-CN.md)) for code style, formatting, and PR guidelines.

```bash
# Setup dev environment
uv sync --group dev

# Format and lint
uv run ruff format . && uv run ruff check .

# Type check
uv run pyright
```

---

中文说明见 [README.zh-CN.md](README.zh-CN.md).
