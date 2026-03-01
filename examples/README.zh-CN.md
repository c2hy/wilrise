# Wilrise 示例项目

独立示例项目，演示如何在新项目中使用 wilrise。  
For English, see [README.md](README.md).

## 建议阅读顺序

示例按数字编号，建议依次阅读以逐步掌握概念：

1. **01_minimal.py** — 最简配置：单一方法 + `app.run()`。
2. **02_routing.py** — 使用 `Router` 和前缀进行路由分组。
3. **03_dependencies.py** — 使用 `Use` 进行依赖注入，包含生成器的自动清理机制。
4. **04_parameters.py** — 参数高阶用法（`Param` 的别名与默认值）以及显式指定 RPC 方法名。
5. **auth_crud/** — 完整应用：SQLAlchemy、JWT 鉴权、CRUD；演示 Pydantic 与 `Use(...)` 结合时的 keyed 传参模式。

## 运行方式

**推荐**：在 `examples` 目录下执行。若在仓库根目录，请使用 `uv run --project examples python examples/<脚本>`（如 `examples/01_minimal.py`）。

**逐步学习示例**：

```bash
cd examples
uv sync
uv run python 01_minimal.py
# 同理运行: 02_routing.py, 03_dependencies.py, 04_parameters.py
```

**Auth + CRUD**（登录与用户 CRUD；需先执行 `uv sync` 安装依赖）：

```bash
cd examples
uv sync
uv run python -m auth_crud.main
```

服务地址为 `http://127.0.0.1:8000`。请求 01 示例：

```bash
curl -X POST http://127.0.0.1:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}'
```

## Auth + CRUD 示例说明

- **技术栈**：SQLAlchemy 2 + SQLite、JWT (PyJWT)、bcrypt 密码哈希、Pydantic 参数校验。
- **RPC 方法**：
  - `auth.login` — 登录；参数 `params: { username, password }`；返回 `{ access_token, token_type }`。
  - `auth.me` — 当前用户信息（需请求头 `Authorization: Bearer <token>`）。
  - `user.create` — 创建用户；参数 `params: { username, password, display_name? }`。
  - `user.list` — 用户列表；参数 `params: { skip?, limit? }`（可选）。
  - `user.get` — 按 ID 查询用户（需登录）；参数 `user_id`。
  - `user.update` — 更新用户（需登录）；参数 `params: { user_id, display_name?, password? }`。
  - `user.delete` — 删除用户（需登录）；参数 `user_id`。

当方法同时包含 Pydantic 参数和 `Use(...)` 依赖时，客户端需按参数名传参（例如在 `params` 键下放请求体）。本示例采用该 **keyed** 写法；若方法只有一个 BaseModel 参数，主 README 推荐 **whole params**（整个 `params` 对象即该模型）。

```bash
# 创建用户（keyed：参数名 "params" + 值对象）
curl -s -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"user.create","params":{"params":{"username":"alice","password":"alice123","display_name":"Alice"}},"id":1}'

# 登录（keyed：参数名 "params"）
curl -s -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"auth.login","params":{"params":{"username":"alice","password":"alice123"}},"id":2}'

# 使用返回的 access_token 调用需登录接口（将 TOKEN 替换为实际 token）
curl -s -X POST http://127.0.0.1:8000 -H "Content-Type: application/json" -H "Authorization: Bearer TOKEN" \
  -d '{"jsonrpc":"2.0","method":"auth.me","params":{},"id":3}'
```

数据库文件默认在 `examples/auth_crud/auth_crud.db`，可通过环境变量 `AUTH_CRUD_DB` 修改路径。本示例为便于排查使用 `debug=True`；生产环境请使用 `debug=False` 或 `from_env()`（见主 README 与 [docs/configuration.md](../docs/configuration.md)）。

### 测试与验证 (pytest)

在 `examples` 目录下（使用 `uv sync` 安装测试依赖）：

```bash
cd examples
uv sync
uv run pytest test_basics.py auth_crud/test_integration.py -v
```

这些测试通过 Starlette TestClient 和临时测试数据库覆盖了所有基本和高级示例的逻辑验证。

### 并发与事务安全测试

`auth_crud/test_concurrent.py` 使用临时 SQLite 库和 httpx ASGI 传输，并发执行：创建 20 个用户、并行登录、并行列表/查询/更新/删除，并断言无事务或会话泄漏（每个请求独立 session，关闭时对未提交变更执行 rollback）。

```bash
uv sync
uv run python -m auth_crud.test_concurrent
```

## 其他用法（见主 README 与 docs）

- **Batch 请求**：一次 POST 发送 JSON-RPC 请求数组，服务端按顺序返回响应数组。见主项目 [README](../README.md#batch-requests)。
- **挂载**：使用 `app.as_asgi()` 得到 ASGI 应用后挂到现有 Starlette/FastAPI 应用下（如 `app.mount("/rpc", rpc.as_asgi())`）。见 [挂载到现有应用](../README.md#mounting-on-an-existing-app)。
- **错误处理**：业务错误用 `RpcError(code, message, data)`；第三方异常用 `set_exception_mapper` 映射为稳定错误码。见 [docs/errors.md](../docs/errors.md)。
