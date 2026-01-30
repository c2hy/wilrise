# 贡献指南

感谢你对 wilrise 的关注。本文档说明如何搭建开发环境、运行测试与代码检查，以及如何提交 Issue 和 Pull Request。

## 开发环境

### 前置要求

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)**（推荐）或 pip

### 克隆与安装

```bash
git clone https://github.com/<your-username>/wilrise.git
cd wilrise
```

使用 uv 安装依赖（含开发依赖）：

```bash
uv sync --group dev
```

使用 pip 时：

```bash
pip install -e ".[pydantic]"
pip install pytest pytest-asyncio httpx pydantic ruff pyright
```

### 使用本地包运行示例

仓库根目录下用 `examples` 作为项目运行：

```bash
uv run --project examples python examples/minimal.py
# 或
uv run --project examples python examples/main.py
```

`examples/pyproject.toml` 通过 `[tool.uv.sources]` 指向本地 wilrise，无需先 `pip install -e .`。

## 代码规范与检查

项目使用 [Ruff](https://docs.astral.sh/ruff/) 做格式与 lint，[Pyright](https://microsoft.github.io/pyright/) 做类型检查。**提交前请本地跑通以下命令。**

### 格式化与 Lint（Ruff）

```bash
# 仅格式化
uv run ruff format .

# 仅检查
uv run ruff check .

# 格式化并检查（推荐提交前执行）
uv run ruff format . && uv run ruff check .
```

### 类型检查（Pyright）

```bash
uv run pyright
```

配置见 `pyproject.toml` 中 `[tool.ruff]` 与 `[tool.pyright]`。

## 运行测试

```bash
uv run pytest
```

或带覆盖率（需先安装 coverage）：

```bash
uv run pytest --cov=wilrise --cov-report=term-missing
```

请确保新增或修改逻辑有对应测试，且 `uv run pytest` 通过。

## 分支策略

项目采用适合开源库的 **双分支** 策略：

- **main**：可发布版本。仅在发版时从 `develop` 合并进来。用语义化版本打 tag（如 `v1.0.0`）。
- **develop**：默认开发分支。所有 PR 都合并到 `develop`，作为下一版本的集成分支。

**流程：**

- **贡献者**：Fork → 从 `develop` 创建功能分支（如 `fix/issue-123`、`feat/add-middleware`）→ 向 **`develop`** 提 PR。
- **维护者**：审查并合并到 `develop`，发版时将 `develop` 合并到 `main` 并打 tag，必要时将 `main` 合并回 `develop` 保持同步。

**分支命名（可选）**：`fix/简短描述`、`feat/简短描述`、`docs/...`，便于区分类型。

## 提交 Issue

- **Bug 报告**：请用 [Bug 报告模板](.github/ISSUE_TEMPLATE/bug_report.md)，并尽量提供最小复现步骤、环境与报错信息。
- **功能建议**：请用 [功能建议模板](.github/ISSUE_TEMPLATE/feature_request.md)，说明使用场景与期望行为。
- 在提 Issue 前可先搜索是否已有类似讨论。

## 提交 Pull Request

1. **Fork 本仓库**，在你自己 fork 的分支上开发。
2. **从最新 `develop` 创建分支并保持同步**，减少冲突：

   ```bash
   git fetch upstream
   git rebase upstream/develop
   ```

3. **本地自检**：
   - `uv run ruff format . && uv run ruff check .`
   - `uv run pyright`
   - `uv run pytest`
4. **提交信息**：建议使用清晰的前缀，例如：
   - `fix: 修复批量请求时错误码为 -32600 时的响应格式`
   - `feat: 支持通过中间件注入 Request`
   - `docs: 在 README 中补充挂载到 FastAPI 的示例`
5. **推送到你的 fork**，然后向本仓库的 **`develop`** 分支发起 PR。
6. 在 PR 描述中简要说明改动动机与测试方式，并勾选 PR 模板中的检查项。

维护者会在 CI 通过后进行代码审查；如需修改，请在同一 PR 内追加提交或 rebase 后强制推送。

---

再次感谢你的贡献。

English: [CONTRIBUTING.md](CONTRIBUTING.md).
