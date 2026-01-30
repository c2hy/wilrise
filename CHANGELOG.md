# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- None yet.

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

[Unreleased]: https://github.com/your-username/wilrise/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-username/wilrise/releases/tag/v0.1.0
