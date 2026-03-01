# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- None yet.

## [0.2.2] - 2025-03-01

### Added

- `Use` in `Annotated`: dependency injection via `Annotated[Session, Use(get_db_session)]` without default value. Type checkers (Pyright/Pylance) infer the parameter type correctly; usage aligns with FastAPI's `Annotated[Type, Depends(dep)]` pattern.

## [0.2.1] - 2025-02-24

### Fixed

- RPC methods can now return Pydantic `BaseModel` instances when `wilrise[pydantic]` is installed. The framework normalizes such results via `model_dump(mode="json")` before the JSON-serializability check and response build, so returning typed response models no longer triggers -32603 "Result is not JSON-serializable".

## [0.2.0] - 2025-02-23

### Added

- Sync RPC methods (`def`) are now executed in a thread pool via `asyncio.to_thread`, matching FastAPI/Starlette
  behavior for synchronous endpoints: blocking I/O in a sync method no longer blocks the event loop or other
  concurrent requests.

### Changed

- Architecture doc: document that sync methods run in thread pool (see `docs/architecture.md`).

## [0.1.2] - 2025-01-30

### Added

- Publish workflow: trigger only when tag is on main; run CI before publishing to PyPI.

### Fixed

- Ruff E501 (docstring line length) and Pyright reportUnnecessaryIsInstance in `wilrise.core`.

## [0.1.1] - 2025-01-30

### Added

- README FAQ: JSON-RPC array vs object params (positional vs named binding) and how to receive an array-of-objects parameter.

## [0.1.0] - 2025-01-30

First public release.

### Added

- JSON-RPC 2.0 server on Starlette (single and batch requests).
- `@app.method` / Router, `Use` dependency injection, `Param` (description, alias).
- Optional Pydantic validation for params and result serialization.
- Extension points: RequestParser, ResponseBuilder, ExceptionMapper, RequestLogger.
- Before/after call hooks, startup/shutdown, middleware, mount on existing app.
- Optional `from_env()` helper to build `Wilrise` kwargs from `WILRISE_*` environment variables.
- Documentation: production readiness (errors, configuration, observability, versioning, runbook, architecture).

[Unreleased]: https://github.com/c2hy/wilrise/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/c2hy/wilrise/releases/tag/v0.2.2
[0.2.1]: https://github.com/c2hy/wilrise/releases/tag/v0.2.1
[0.2.0]: https://github.com/c2hy/wilrise/releases/tag/v0.2.0
[0.1.2]: https://github.com/c2hy/wilrise/releases/tag/v0.1.2
[0.1.1]: https://github.com/c2hy/wilrise/releases/tag/v0.1.1
[0.1.0]: https://github.com/c2hy/wilrise/releases/tag/v0.1.0
