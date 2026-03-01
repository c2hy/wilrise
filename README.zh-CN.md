# wilrise (中文)

Wilrise 是一个基于 [Starlette](https://www.starlette.io/) 构建的 **服务端 JSON-RPC 框架**。

它的目标受众是：希望在保留 ASGI 生态优势（如可挂载到 FastAPI/Starlette、复用中间件、全链路异步）的前提下，获得 RPC 语义（面向方法的 API 设计、自带批量请求机制）的团队。

本文档假设你已熟悉 **JSON-RPC 2.0** 规范。框架仅实现服务端；客户端你可以使用任何符合规范的 JSON-RPC 2.0 库。

## 安装

```bash
# 使用 uv (推荐)
uv add wilrise

# 或使用 pip
pip install wilrise
```

如果你需要 Pydantic 参数校验功能，从而在参数类型错误时返回明确的 `Invalid params` (-32602) 错误码，请安装可选依赖：`uv add "wilrise[pydantic]"`。

## 快速开始

**1. 编写一个最小服务** (如 `main.py`)：

```python
from wilrise import Wilrise

app = Wilrise()

@app.method
def add(a: int, b: int) -> int:
    return a + b

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
```

**2. 运行服务端**：

```bash
uv run python main.py
```

**3. 发起请求**：

```bash
curl -X POST http://127.0.0.1:8000/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0", "method":"add", "params":{"a":1, "b":2}, "id":1}'
```

响应结果：`{"jsonrpc":"2.0","result":3,"id":1}`

## 通过示例学习

为了快速掌握该框架，我们强烈建议你查看 `examples/` 目录。其中包含了循序渐进、可直接运行的教学示例：

1. **[01_minimal.py](examples/01_minimal.py)** — 最基础的起步。
2. **[02_routing.py](examples/02_routing.py)** — 使用 `Router` 与前缀对方法进行模块化路由。
3. **[03_dependencies.py](examples/03_dependencies.py)** — 依赖注入（`Use`）。
4. **[04_parameters.py](examples/04_parameters.py)** — 进阶参数（`Param` 别名与默认值）。
5. **[auth_crud/](examples/auth_crud/)** — 包含 SQLAlchemy、JWT 鉴权以及完整 CRUD 的工程化示例。

在 `examples` 目录下运行示例：

```bash
cd examples
uv sync
uv run python 01_minimal.py
```

更多详见 [examples/README.zh-CN.md](examples/README.zh-CN.md)。

## 文档索引 (Documentation Index)

关于进阶主题、生产环境最佳实践以及深度解析，请查阅 `docs/` 目录下的专题文档：

- 📖 **架构与生命周期**: 请求如何从 HTTP 到 JSON-RPC 再流转回来的全过程。[阅读 architecture.md](docs/architecture.md)
- ⚙️ **配置管理**: 环境变量、请求体积限制、Debug 模式等。[阅读 configuration.md](docs/configuration.md)
- 🚨 **错误与异常模型**: 协议错误 vs 应用错误、`RpcError`、如何映射第三方依赖的异常。[阅读 errors.md](docs/errors.md)
- 📊 **可观测性**: 记录请求日志、Trace ID 以及如何集成 OpenTelemetry 或 Loguru。[阅读 observability.md](docs/observability.md)
- 🛠 **排障 Runbook**: 遇到 413、-32600 报错或 -32603 Internal Error 怎么查。[阅读 runbook.md](docs/runbook.md)
- 🔄 **从 FastAPI 迁移**: 如果你熟悉 FastAPI，查看对应的概念映射。[阅读 migration-from-fastapi.md](docs/migration-from-fastapi.md)
- 🚀 **生产环境 Checklist**: 上线前必须检查的清单。[阅读 PRODUCTION_READINESS_CHECKLIST.md](docs/PRODUCTION_READINESS_CHECKLIST.md)

## 参与开发

欢迎提交 Bug 报告、新特性需求或 Pull Request。有关代码风格、格式化检查与 PR 规范，请参考 [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)。

```bash
# 初始化开发环境
uv sync --group dev

# 格式化与 Lint
uv run ruff format . && uv run ruff check .

# 类型检查
uv run pyright
```

---

For the English version, see [README.md](README.md).
