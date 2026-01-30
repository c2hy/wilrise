# Contributing

Thanks for your interest in wilrise. This guide explains how to set up the development environment, run tests and code checks, and how to submit issues and pull requests.

## Development environment

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip

### Clone and install

```bash
git clone https://github.com/<your-username>/wilrise.git
cd wilrise
```

Install dependencies including dev groups with uv:

```bash
uv sync --group dev
```

With pip:

```bash
pip install -e ".[pydantic]"
pip install pytest pytest-asyncio httpx pydantic ruff pyright
```

### Running examples with the local package

From the repo root, run the `examples` project:

```bash
uv run --project examples python examples/minimal.py
# or
uv run --project examples python examples/main.py
```

The `examples/pyproject.toml` points at the local wilrise via `[tool.uv.sources]`, so you don’t need to `pip install -e .` first.

### Security

- **No secrets in code.** Keys, database URLs, JWT secrets, and similar must be read from environment variables or a secrets manager. Example projects (e.g. `examples/auth_crud`) use placeholders or `os.environ.get("...")` only; never commit real credentials.
- **Production:** Keep `debug=False`; configure via environment variables where possible (see [docs/configuration.md](docs/configuration.md)).

## Code style and checks

The project uses [Ruff](https://docs.astral.sh/ruff/) for formatting and linting and [Pyright](https://microsoft.github.io/pyright/) for type checking. **Run the commands below locally before submitting.**

### Format and lint (Ruff)

```bash
# Format only
uv run ruff format .

# Lint only
uv run ruff check .

# Format and lint (recommended before commit)
uv run ruff format . && uv run ruff check .
```

### Type check (Pyright)

```bash
uv run pyright
```

Configuration is in `[tool.ruff]` and `[tool.pyright]` in `pyproject.toml`.

## Running tests

```bash
uv run pytest
```

With coverage (install coverage first if needed):

```bash
uv run pytest --cov=wilrise --cov-report=term-missing
```

Please add or update tests for new or changed behavior and ensure `uv run pytest` passes.

## Branch strategy

The project uses a **two-branch** strategy suitable for open source libraries:

- **main**：Production-ready code; every commit is a potential release. Only updated by merging from `develop` when releasing a new version. Tagged with semantic versions (e.g. `v1.0.0`).
- **develop**：Default branch for development. All PRs target `develop`. Integration branch for the next release.

**Workflow:**

- **Contributors**: Fork → create a feature branch from `develop` (e.g. `fix/issue-123` or `feat/add-middleware`) → open PR **into `develop`**.
- **Maintainers**: Merge PRs into `develop` after review and CI. When ready to release, merge `develop` into `main`, tag the version, then merge `main` back into `develop` to keep them in sync (or use a release PR).

**Branch naming (optional):** `fix/short-desc`, `feat/short-desc`, `docs/...` to keep history clear.

## Submitting issues

- **Bug reports**: Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) and include minimal steps to reproduce, environment, and error output when possible.
- **Feature requests**: Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md) and describe the use case and desired behavior.
- Search existing issues before opening a new one.

## Submitting pull requests

1. **Fork the repo** and work in your own fork.
2. **Create a branch from the latest `develop`** and keep it updated to reduce conflicts:

   ```bash
   git fetch upstream
   git rebase upstream/develop
   ```

3. **Run checks locally**:
   - `uv run ruff format . && uv run ruff check .`
   - `uv run pyright`
   - `uv run pytest`
4. **Commit messages**: Use a clear prefix, e.g.:
   - `fix: correct response format for -32600 on batch requests`
   - `feat: allow injecting Request via middleware`
   - `docs: add FastAPI mount example to README`
5. **Push to your fork** and open a PR against this repo’s **`develop`** branch.
6. In the PR description, briefly explain the change and how you tested it, and complete the checklist in the PR template.

Maintainers will review after CI passes. If changes are requested, push additional commits or rebase and force-push in the same PR.

---

Thank you for contributing.

中文版见 [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)。
