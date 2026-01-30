# wilrise

Wilrise — 基于 Starlette 的现代异步 JSON-RPC 框架，简洁易上手。

本文档默认假定你已熟悉 **JSON-RPC 2.0**（请求/响应格式、method、params、id、错误码等）。本框架仅实现服务端；调用方式请使用任意符合 JSON-RPC 2.0 的客户端。

## 安装

```bash
# 使用 uv（推荐）
uv add wilrise

# 或 pip
pip install wilrise
```

安装后请在代码中使用 `from wilrise import Wilrise`。若需要参数校验（在类型错误时返回明确的 -32602 而非 -32603），请安装可选依赖：`uv add "wilrise[pydantic]"` 或 `pip install "wilrise[pydantic]"`。

## 5 分钟上手

**1. 写一个最小服务**（例如 `main.py`）：

```python
from wilrise import Wilrise

app = Wilrise()

@app.method
def add(a: int, b: int) -> int:
    return a + b

# 推荐：app.run() 使用 uvicorn 且默认关闭 access_log，输出 JSON-RPC 风格日志
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
```

**2. 启动服务**（在包含 `main.py` 的目录下）：

```bash
uv run python main.py
```

控制台会看到 JSON-RPC 风格日志（如 `JSON-RPC add → 200 in 12.50ms`），而不会刷屏 "POST / 200"。若需交给其他 ASGI 服务器或挂到现有应用下，请使用 `app.as_asgi()`（见下文 [挂载](#挂载到现有应用)）。

若使用仓库内 **examples**，在项目根目录执行：

```bash
uv run --project examples python examples/minimal.py
```

**3. 发请求**（单次调用）：

```bash
curl -X POST http://127.0.0.1:8000/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}'
```

响应示例：`{"jsonrpc":"2.0","result":3,"id":1}`。

- 请求体必须是 JSON，且包含 `"jsonrpc":"2.0"`、`"method"`（方法名）、可选 `"params"`（对象或数组）、可选 `"id"`（通知请求可省略，无响应体）。

### 批处理请求

一次 POST 发送 JSON-RPC 请求数组；响应为**同顺序**的响应数组。无 `id` 的通知请求不会在响应数组中占位。若全部为通知，服务器返回 204 No Content。单个请求失败不会导致整批失败，每个请求各自返回成功或错误。

## 进阶：依赖注入与路由分组

使用 **Router** 和 `include_router(router, prefix="...")` 按模块分组方法（如 `math.add`、`user.get`），参见 `examples/main.py`。

```python
from wilrise import Router, Use, Wilrise
from starlette.requests import Request

app = Wilrise()

# 依赖提供者（可从 request、连接池等获取）
async def get_db_session(request: Request):
    return DBSession()  # 示例：从 pool、request.state 等获取

@app.method
async def add(a: int, b: int) -> int:
    return a + b

@app.method
async def get_user(user_id: int, db: DBSession = Use(get_db_session)) -> dict | None:
    return await db.get_user(user_id)  # db 由 Use 注入

# Use(provider) 若抛异常，请求会返回 -32603（Internal error），可视为依赖失败（如 DB/鉴权）。
# 独立运行：app.run()；挂载到现有应用：app.as_asgi()
```

## 前置知识

- 基于 **Starlette**，若你熟悉 ASGI 或 FastAPI，会很快上手（`@app.method` 类似路由，`Use` 与 FastAPI 的 `Depends` 类似，用于依赖注入）。
- **未安装**可选 Pydantic 依赖时，参数类型**不会**被校验；传错类型（如应为 int 却传字符串）会导致 **Internal error**（-32603）或未定义行为。若希望类型错误时返回明确的 **Invalid params**（-32602），请安装：`uv add "wilrise[pydantic]"`（见下文 [Pydantic 参数校验（可选）](#pydantic-参数校验可选)）。

## 配置选项

`Wilrise` 支持以下初始化参数：

- **debug**（默认 `False`）：为 `True` 时在错误响应中返回完整异常信息。**生产环境请保持 `False`** 以避免泄露敏感信息。
- **max_batch_size**（默认 `50`）：批处理请求的最大数量，超出返回 -32600。
- **max_request_size**（默认 `1024*1024`，1MB）：请求体最大字节数；**仅当存在 `Content-Length` 时检查**——无该头的请求不会被框架限制大小，超出时返回 413。需无论是否有该头都严格限制时（如生产环境），请使用反向代理或自定义中间件。
- **log_requests**（默认 `True`）：为 `True` 时按 JSON-RPC 风格记录每条请求：方法名、HTTP 状态、耗时（如 `JSON-RPC math.add → 200 in 12.50ms`；批处理为 `JSON-RPC batch(n) [method1, ...] → 200 in 45ms`）。

```python
# 生产环境示例
app = Wilrise(debug=False, max_batch_size=50, max_request_size=1024 * 1024)

# 开发环境：开启 debug 便于排查
app = Wilrise(debug=True)
```

### 启动方式

- **推荐**：`app.run(host="127.0.0.1", port=8000)` — 内部使用 uvicorn 且默认关闭 access_log，只输出 JSON-RPC 风格日志（方法名、状态码、耗时）。可选参数：`app.run(host="0.0.0.0", port=8000, access_log=True, **uvicorn_kwargs)`。
- **可选**：若需传入其他 uvicorn 参数，可使用 `uvicorn.run(app.as_asgi(), host="127.0.0.1", port=8000, access_log=False)`。
- **挂载**：使用 `app.as_asgi()` 得到 Starlette 应用后挂到现有应用下（见下文 [挂载到现有应用](#挂载到现有应用)）。

## 中间件

可通过 `add_middleware` 添加 Starlette 中间件（如 CORS、认证、日志等）：

```python
from starlette.middleware.base import BaseHTTPMiddleware

app = Wilrise()

class CustomMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 在请求前处理...
        response = await call_next(request)
        # 在响应后处理...
        return response

app.add_middleware(CustomMiddleware)
```

## 示例项目

`examples/` 为演示项目，与在新项目中使用 wilrise 的目录结构一致。建议阅读顺序：**minimal.py** → **main.py** → **auth_crud/**（见 [examples/README.zh-CN.md](examples/README.zh-CN.md)）。

```text
examples/
├── pyproject.toml   # 依赖 wilrise
├── minimal.py       # 最小示例：仅 add 方法 + 启动
├── main.py          # 完整示例：Router、Param、Use、别名等
└── auth_crud/       # 完整应用：SQLAlchemy、JWT 鉴权、CRUD（whole-params 传参）
```

- **最小示例**（只跑一个 `add` 方法）：

  ```bash
  cd examples && uv sync && uv run python minimal.py
  ```

- **完整示例**（Router、依赖注入、Param 别名等）：

  ```bash
  cd examples && uv sync && uv run python main.py
  ```

- **Auth + CRUD**（登录与用户 CRUD；需先执行 `uv sync`）：

  ```bash
  cd examples && uv sync && uv run python -m auth_crud.main
  ```

从仓库根目录运行：

```bash
uv run --project examples python examples/minimal.py
# 或
uv run --project examples python examples/main.py
# 或
uv run --project examples python -m auth_crud.main
```

> 本地开发时 `pyproject.toml` 通过 `[tool.uv.sources]` 指向当前 wilrise；从 PyPI 安装后请删除该段。

## Pydantic 参数校验（可选）

**未安装** `pydantic` 时，参数类型（如 `int`、`str`）**不会**被校验；传错类型可能导致 `-32603` 或未定义行为。需要声明式校验时请安装：

```bash
uv add "wilrise[pydantic]"
# 或 pip install "wilrise[pydantic]"
```

- **单参数且类型为 BaseModel**：两种合法写法；**推荐**使用 **whole params**（整个 `params` 即该模型）。客户端与服务端应约定一致。
  - **Whole params**（推荐）：`"params": {"a": 1, "b": 2}` → 整体校验为 `AddParams`。
  - **带键**：`"params": {"params": {"a": 1, "b": 2}}` → 仅对键 `params` 的值做校验。
- **多参数时**：任意参数注解为 `BaseModel` 时，该参数对应的 JSON 会被校验并反序列化为模型实例。
- 所有 `-32602` 响应统一使用 `error.data.validation_errors`（`{loc, msg, type}` 列表），便于客户端统一处理。
- **返回值**必须可 JSON 序列化，否则服务器返回 `-32603`。

示例：

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

请求 `{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}` 会得到 `result: 3`；若 `params` 类型不符则得到 `-32602` 及 `validation_errors`。

## 错误码速查（JSON-RPC 2.0）

- **-32700** Parse error — 请求体不是合法 JSON。
- **-32600** Invalid Request — 缺少 `jsonrpc`/`method`、method 非字符串、params 非对象/数组、请求体过大、批处理超限等。
- **-32601** Method not found — 调用的 method 未注册。
- **-32602** Invalid params — 缺少必填参数、Pydantic 校验失败等。所有 `-32602` 响应统一使用 `error.data.validation_errors`（`{loc, msg, type}` 列表），便于客户端统一处理。
- **-32603** Internal error — 方法或依赖（Use）抛异常、或返回值不可 JSON 序列化（生产下不返回具体信息）。生产环境建议用 `set_exception_mapper` 将已知异常（如 DB、鉴权）映射为固定应用码，使客户端得到可操作的错误而非笼统的 "Internal error"。详见 [docs/errors.md](docs/errors.md)。

## 挂载到现有应用

**挂到现有应用**：`app.mount("/rpc", rpc.as_asgi())`（FastAPI）或 Starlette 的 `routes=[Mount("/rpc", app=rpc.as_asgi())]`。请求地址为 `http://host/rpc`。

## Param 与 Use

- **Param(description=..., alias=...)**：`description` 仅作元数据（如自建文档/OpenRPC）；`alias` 用于客户端传不同键名（如 `userId` 代替 `user_id`）。
- **Use(provider)**：注入 provider 的返回值。若 provider 抛异常，请求返回 `-32603`（Internal error），可视为依赖失败（如 DB/鉴权）。

## 常见问题

- **params 用数组传和用对象传，服务端怎么接收？**  
  JSON-RPC 2.0 规定 `params` 可以是**数组**或**对象**。若客户端用**数组**传参（如 `"params": [1, 2]`），服务端会**按位置**绑定：第一个元素对应第一个参数，第二个对应第二个，以此类推。若用**对象**传参（如 `"params": {"a": 1, "b": 2}`），则**按名称**绑定。方法签名需与之匹配：按位置时，参数个数与顺序需与数组一致；按名称时，键名需与参数名（或 alias）一致。

  **若服务端要接收“对象数组”这类参数**（例如一批要批量创建的元素）：该数组是**某一个参数的值**。用**按位置**传参时，客户端传的 `params` 是一个数组，其中**第一个元素**就是你的对象数组：`"params": [[{"id": 1}, {"id": 2}]]` → 方法的第一个参数收到这个内层数组。用**按名称**传参时，客户端传一个带单个键的对象：`"params": {"items": [{"id": 1}, {"id": 2}]}` → 名为 `items` 的参数收到该数组。例如方法 `def batch_create(items: list[dict]) -> int` 可用 `"params": {"items": [...]}` 或 `"params": [[...]]` 调用。

- **客户端如何知道有哪些方法？**  
  JSON-RPC 2.0 不强制 schema；本框架不提供 OpenAPI 或内置方法发现。可按需自建一个 RPC 方法返回方法名列表（及参数说明），或提供 OpenRPC / 自描述文档。

- **为什么要求 Python 3.12+？**  
  项目采用单一现代版本以简化类型与维护；目前不计划支持更早的 Python 版本。

## 贡献

欢迎提交 Bug 报告、功能建议和 Pull Request。开发环境、代码风格与提交流程见 [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)（[English](CONTRIBUTING.md)）。

## 项目结构

- **wilrise** — 核心实现；可选配置见 `wilrise.config.from_env`。
- **examples/** — 演示项目（含最小示例与完整功能示例）。
- **docs/** — 生产相关： [errors](docs/errors.md)、[configuration](docs/configuration.md)、[observability](docs/observability.md)、[versioning](docs/versioning.md)、[runbook](docs/runbook.md)、[architecture](docs/architecture.md)、[production checklist](docs/PRODUCTION_READINESS_CHECKLIST.md)。

---

开发与代码风格见主 [README.md](README.md) 中的 “Development and code style” 小节；如何参与贡献见 [CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)（[English](CONTRIBUTING.md)）。
