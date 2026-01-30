# 错误模型与错误分层

本文档说明 wilrise 中的错误分层、应用错误码约定、可重试策略，以及 `ExceptionMapper` 与 `RpcError` 的优先级。

## 错误分层与使用场景

### 协议层（-32700 ～ -32603）

由框架处理，业务一般不直接返回。

- **-32700**（Parse error）：请求体不是合法 JSON。
- **-32600**（Invalid Request）：缺少 `jsonrpc`/`method`、body 过大、batch 超限等。
- **-32601**（Method not found）：调用的方法未注册。
- **-32602**（Invalid params）：缺少必填参数、Pydantic 校验失败等。
- **-32603**（Internal error）：方法或 Use 依赖抛异常、结果不可 JSON 序列化。

**生产环境 -32603 排查**：`debug=False` 时客户端仅收到 `"Internal error"`，无堆栈。建议用 `set_exception_mapper` 将已知异常（如 DB 连接失败、超时、鉴权失败）映射为固定应用码或协议错误，并在 `error.data` 中提供 `retriable` 等字段；未映射的异常才落在 -32603，便于日志与监控区分。

### 生产环境遇到 -32603 时如何排查

- **不要**在生产环境开启 `debug=True`（会泄露堆栈与内部信息）。
- 使用 **`set_exception_mapper`** 将已知的第三方异常（DB、HTTP 客户端、鉴权库等）映射为固定错误码和 `error.data`，这样只有未预期的异常才会落到 -32603。
- 在 **结构化日志**中记录 `request_id`（或 `X-Request-ID` / `RpcContext.http_request_id`）；框架在非 debug 的 -32603 响应中会在 `error.data.request_id` 中返回该值，便于在日志中检索同一次请求。
- 通过 **`add_request_logger`** 或中间件统一输出请求/耗时/状态，便于与客户端报告的 `request_id` 关联。

### 应用层（-32099 ～ -32000）

业务通过 `RpcError(code, message, data)` 主动返回；推荐在 `data` 中携带稳定的 `code`（如 `auth_failed`）供前端分支。

```python
from wilrise import RpcError

# 推荐：data 中带稳定 code，便于前端统一处理
raise RpcError(-32001, "Invalid username or password", data={"code": "auth_failed"})
```

### 依赖 / 基础设施异常

通过 `set_exception_mapper` 将第三方异常映射为协议错误或固定应用码，避免直接暴露 -32603 与堆栈。

```python
from wilrise import Wilrise, ExceptionMapper
from wilrise.context import RpcContext
from wilrise.errors import INTERNAL_ERROR

def map_db_error(exc: Exception, context: RpcContext) -> tuple[int, str, object] | None:
    if isinstance(exc, ConnectionError):
        return (INTERNAL_ERROR, "Service temporarily unavailable", {"retriable": True})
    return None

app = Wilrise()
app.set_exception_mapper(map_db_error)
```

## 应用错误码注册表（推荐）

建议在团队内维护一张「应用错误码注册表」，新增业务错误码时登记，避免冲突与重复。

- **-32001**（data.code: `auth_failed`）：认证失败（用户名/密码错误等），不可重试。
- **-32002**（data.code: `permission_denied`）：权限不足，不可重试。
- **-32003**（data.code: `resource_not_found`）：资源不存在，不可重试。
- **-32004**（data.code: `conflict`）：资源冲突（如重复创建），不可重试。
- **-32010**（data.code: `rate_limited`）：限流，可重试（带重试间隔）。

约定：新增业务错误码需在团队内登记；前端/客户端按 `error.data.code` 做分支，不依赖 `message` 文案。

## 可重试 vs 不可重试

- **不建议重试**：-32600、-32601、-32602（参数/方法问题，重试无意义）、-32001 认证失败、-32002 权限不足等。
- **可考虑重试**：部分 -32603（如依赖临时不可用）、5xx 场景；建议在 `error.data` 中约定 `retriable: bool`，便于客户端统一策略。

在 `ExceptionMapper` 或 `RpcError` 的 `data` 中返回 `retriable: true/false` 即可，框架不强制该字段。

## ExceptionMapper 与 RpcError 的优先级

**处理顺序**：先走 `ExceptionMapper.map_exception()`；若返回 `None`，再按 `RpcError` 或其它未捕获异常处理（最终可能返回 -32603）。

- **业务异常**：尽量用 `RpcError` 在方法内或 Use 依赖内抛出，语义清晰、便于前端按码处理。
- **第三方库异常**：用 `set_exception_mapper` 统一映射为协议错误或固定应用码，避免泄露内部信息与堆栈。

详见 [Error codes (JSON-RPC 2.0)](../README.md#error-codes-json-rpc-20)。
