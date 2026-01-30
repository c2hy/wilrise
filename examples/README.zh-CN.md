# Wilrise 示例项目

独立示例项目，演示如何在新项目中使用 wilrise。  
For English, see [README.md](README.md).

## 建议阅读顺序

1. **minimal.py** — 先跑起来：一个方法 + `app.run()`。
2. **main.py** — Router、依赖注入（`Use`）及可选写法（Param 别名、显式方法名）。
3. **auth_crud/** — 完整应用：SQLAlchemy、JWT 鉴权、CRUD；当方法同时有 Pydantic 与 `Use(...)` 时使用 keyed 传参。

## 文件说明

- **minimal.py** — 最简示例：单个 `add` 方法并运行，适合首次使用。
- **main.py** — 完整示例：Router、`Param` 描述/别名、`Use` 依赖注入、显式方法名。
- **auth_crud/** — 登录与 CRUD：SQLAlchemy (SQLite)、JWT 登录、用户增删改查。

## 运行方式

**推荐**：在 `examples` 目录下执行。若在仓库根目录，请使用 `uv run --project examples python examples/<脚本>`（如 `examples/minimal.py`）。

**最简示例**（仅加法）：

```bash
cd examples
uv sync
uv run python minimal.py
```

**完整示例**（math.add、get_user、getUser、get_user_by_alias 等）：

```bash
cd examples
uv sync
uv run python main.py
```

**Auth + CRUD**（登录与用户 CRUD；需先执行 `uv sync` 安装 sqlalchemy、pyjwt、bcrypt 等）：

```bash
cd examples
uv sync
uv run python -m auth_crud.main
```

**从仓库根目录运行**（效果相同）：

```bash
uv run --project examples python examples/minimal.py
# 或
uv run --project examples python examples/main.py
# 或
uv run --project examples python -m auth_crud.main
```

服务地址为 `http://127.0.0.1:8000`。示例请求：

```bash
curl -X POST http://127.0.0.1:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1}'
```

## main.py 演示要点

- **推荐默认**：方法名 = 函数名（如 `get_user` → RPC 方法 `get_user`）、普通参数、用 Router + prefix 分组。
- **Router + 前缀**：`math_router` 挂载前缀 `math.` → `math.add`、`math.multiply` 等。
- **Use**：`db: DBSession = Use(get_db_session)` 依赖注入（支持同步/异步提供者）。
- **按需使用**：`Param(alias="userId")` 用于与前端命名一致（如 camelCase）；`@app.method("getUser")` 固定 RPC 方法名；`Param(description="...")` 用于文档。

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

### 并发与事务安全测试

`auth_crud/test_concurrent.py` 使用临时 SQLite 库和 httpx ASGI 传输，并发执行：创建 20 个用户、并行登录、并行列表/查询/更新/删除，并断言无事务或会话泄漏（每个请求独立 session，关闭时对未提交变更执行 rollback）。

```bash
uv sync
uv run python -m auth_crud.test_concurrent
```

通过即表示：并发创建/登录/读/写/删均无交叉污染，连接池与 session 隔离正常。

## 其他用法（见主 README 与 docs）

- **Batch 请求**：一次 POST 发送 JSON-RPC 请求数组，服务端按顺序返回响应数组。见主项目 [README](../README.md#batch-requests)。
- **挂载**：使用 `app.as_asgi()` 得到 ASGI 应用后挂到现有 Starlette/FastAPI 应用下（如 `app.mount("/rpc", rpc.as_asgi())`）。见 [挂载到现有应用](../README.md#mounting-on-an-existing-app)。
- **错误处理**：业务错误用 `RpcError(code, message, data)`；第三方异常用 `set_exception_mapper` 映射为稳定错误码。见 [docs/errors.md](../docs/errors.md)。
