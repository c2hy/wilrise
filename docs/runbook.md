# 运维与排障 Runbook

本文档提供 wilrise 服务常见问题与排查思路，便于运维与排障。

## 常见问题

### HTTP 413（Request body too large）

- **原因**：请求体超过 `max_request_size`（默认 1MB），且请求带有 `Content-Length` 头。
- **处理**：
  - 客户端：减小单次请求体，或拆成多次请求 / batch 中单条体积减小。
  - 服务端：若确有需求，可调大 `max_request_size`（如 `Wilrise(max_request_size=2*1024*1024)` 或通过 `WILRISE_MAX_REQUEST_SIZE` 环境变量）；注意反向代理（如 nginx）的 `client_max_body_size` 也需相应调大。
- **注意**：未带 `Content-Length` 时框架不校验 body 大小；若需严格限制，请使用反向代理或自定义 middleware 做校验。

### -32600（Invalid Request）：batch 超限

- **原因**：单次 POST 中 JSON 数组长度超过 `max_batch_size`（默认 50）。
- **处理**：
  - 客户端：单次 batch 请求数不超过 `max_batch_size`，或拆成多个 HTTP 请求。
  - 服务端：若业务允许，可调大 `max_batch_size`（或 `WILRISE_MAX_BATCH_SIZE`），注意内存与延迟影响。

### -32603（Internal error）排查思路

- **含义**：方法或 Use 依赖抛出未映射异常，或返回结果不可 JSON 序列化。
- **排查**：
  1. **看日志**：框架在 `log_requests=True` 时会打 `logger.error(..., exc_info=True)`，查看 `request_id`、`method`、`error_type`、`error_message` 及堆栈。
  2. **临时开 debug**：在**非生产**环境设置 `Wilrise(debug=True)` 或 `WILRISE_DEBUG=1`，错误响应中会包含异常类型与消息（**生产勿开**，避免泄露敏感信息）。
  3. **依赖异常**：若异常来自 DB、HTTP 客户端等，可用 `set_exception_mapper` 将之映射为固定应用码或协议错误，并在 mapper 内打日志便于定位。
  4. **结果不可序列化**：检查方法返回值是否为 JSON 可序列化（如无自定义类型、datetime 需转成字符串等）。

### -32602（Invalid params）

- **含义**：缺少必填参数或 Pydantic 校验失败。
- **处理**：查看响应中 `error.data.validation_errors`（列表，含 `loc`、`msg`、`type`），对照方法签名与请求 params 修正客户端传参。

### -32601（Method not found）

- **含义**：调用的 RPC 方法名未注册。
- **处理**：确认方法名拼写、前缀（若使用 Router 的 prefix）与注册顺序（`include_router` 在请求到达前完成）。

## 日志中看什么

- **request_id** / **http_request_id**：来自 HTTP 头 `X-Request-ID`，用于关联同一次请求的日志与下游调用。
- **rpc_methods**：本次请求调用的 RPC 方法名（单条或 batch 列表）。
- **status_code**：HTTP 状态码（请求日志 `extra` 中保留）。
- **rpc_codes** / 日志消息中的状态：JSON-RPC 错误码（如 -32601、-32001）或 `OK`，便于区分业务错误与成功。
- **duration_ms**：请求耗时（毫秒），便于发现慢请求。

建议在网关或入口统一设置 `X-Request-ID`，便于全链路排查。详见 [Observability](observability.md)。

## 临时开启 debug 定位问题

仅在**非生产**、临时排查时使用：

```python
app = Wilrise(debug=True)
# 或通过环境变量：WILRISE_DEBUG=1
```

开启后，-32603 等错误的响应中会包含 `error.data.type`（异常类型）和完整 `message`。**生产环境务必保持 `debug=False`**，避免泄露内部信息。

## 多 worker 部署

- wilrise 应用本身无状态，可多 worker 运行（如 uvicorn workers、gunicorn + uvicorn worker）。
- 共享资源（如 DB 连接池、Redis 客户端）建议在 **startup** 钩子中初始化，并在 **shutdown** 钩子中关闭，确保每个 worker 进程有自己的连接池，避免跨进程共享连接。

---

错误模型与分层见 [Errors](errors.md)，配置见 [Configuration](configuration.md)。
