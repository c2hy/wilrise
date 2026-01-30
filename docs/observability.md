# 可观测性：日志与追踪

本文档说明如何配置 wilrise 的日志命名、结构化输出、请求 ID 与追踪，以及可选的 OpenTelemetry / Metrics 集成方式。

## Logger 命名与层级

框架默认使用 `logging.getLogger("wilrise.core")`。你可以通过 **`logger`** 和 **`log_level`** 参数控制日志输出：

- **logger**（可选）：传入自定义 `logging.Logger`（如 `logging.getLogger("app.rpc")`），框架的请求/错误日志都通过该 logger 输出，便于按应用配置 Handler 与级别。
- **log_level**（可选）：若设置，会调用 `logger.setLevel(log_level)`，仅发出不低于该级别的日志（例如生产环境设 `logging.WARNING`，则成功请求的 INFO 不输出，错误仍以 ERROR/WARNING 输出）。

```python
import logging
from wilrise import Wilrise

# 方式一：传入自定义 logger，在外部配置级别与 Handler
app_logger = logging.getLogger("app.rpc")
app_logger.setLevel(logging.INFO)
app = Wilrise(logger=app_logger)

# 方式二：仅限制级别（使用默认 logger）
app = Wilrise(log_level=logging.WARNING)  # 生产：只打 WARNING/ERROR，不打 INFO 成功请求

# 方式三：同时指定 logger 与级别
app = Wilrise(logger=logging.getLogger("app.rpc"), log_level=logging.WARNING)
```

若不传 `logger`，可继续对 **`wilrise`** 命名空间统一配置级别与 Handler：

```python
logging.getLogger("wilrise").setLevel(logging.WARNING)
```

## 教程：使用 Loguru 作为日志后端

框架内部使用标准库 `logging`；若你希望**所有日志（包括 wilrise 的请求/错误日志）统一由 [Loguru](https://github.com/Delgan/loguru) 输出**，无需修改 wilrise 源码，只需把标准库的 logger 交给 Loguru 接管即可。

### 思路

wilrise 仍使用 `logging.getLogger(...)` 打日志；我们在应用启动时给该 logger 挂一个 **InterceptHandler**，把标准库的 `LogRecord` 转发给 Loguru，这样格式、输出目标（文件/控制台/轮转等）都由 Loguru 配置。

### 步骤一：安装 Loguru

```bash
uv add loguru
# 或 pip install loguru
```

### 步骤二：定义 InterceptHandler 并配置 wilrise 的 logger

在创建 `Wilrise` **之前**，先配置好用于 wilrise 的 stdlib logger，并将其 handler 设为转发到 Loguru 的 `InterceptHandler`：

```python
import logging
from loguru import logger as loguru_logger

from wilrise import Wilrise


class InterceptHandler(logging.Handler):
    """将标准库 logging 的 LogRecord 转发给 Loguru。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


# 让 wilrise 使用的 logger 把日志交给 Loguru
wilrise_logger = logging.getLogger("wilrise.core")
wilrise_logger.handlers = [InterceptHandler()]
wilrise_logger.setLevel(logging.INFO)

# 创建应用时传入该 logger（可选：同时设置 log_level）
app = Wilrise(logger=wilrise_logger, log_level=logging.INFO)


@app.method
def add(a: int, b: int) -> int:
    return a + b


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
```

之后所有 wilrise 的请求/错误日志都会经由 Loguru 输出，你可以在应用入口处用 `loguru_logger.add(...)` 配置格式、文件、轮转等。

### 可选：只拦截 wilrise 命名空间

若只想把 **wilrise** 的日志交给 Loguru，其他库仍用标准库 Handler，可以只给 `wilrise` 的 logger 加 `InterceptHandler`：

```python
wilrise_logger = logging.getLogger("wilrise")
wilrise_logger.handlers = [InterceptHandler()]
wilrise_logger.setLevel(logging.INFO)
# 不传 logger 时，框架使用 logging.getLogger("wilrise.core")，会继承 wilrise 的配置
app = Wilrise(log_level=logging.INFO)
```

### 说明

- 框架的 `logger` 参数类型为 `logging.Logger`，因此传入的必须是标准库的 Logger 实例；通过 InterceptHandler 将“输出”交给 Loguru，即可在不改类型、不改框架代码的前提下使用 Loguru。
- 若希望**直接把** `loguru.logger` 对象传给 `Wilrise(logger=...)`，当前不支持：框架会调用 `logger.setLevel()` 以及 `extra=`、`exc_info=True` 等标准库接口，与 Loguru 的 API 不一致。使用上述拦截方式即可兼顾两者。

## 内置请求日志

当 `log_requests=True`（默认）时，框架会为每次请求打一条 INFO 日志，并附带 `extra`：

- `request_id`：来自 HTTP 头 `X-Request-ID`，若未设置则为 `"unknown"`
- `rpc_methods`：本次请求的 RPC 方法名列表（单请求一个元素，batch 为多个）
- `status_code`：HTTP 状态码（保留用于兼容）
- `duration_ms`：请求耗时（毫秒）
- `rpc_codes`：当存在 JSON-RPC 错误时，为错误码列表（单条为 `[code]`，batch 为各条错误码）；成功或无 body 时不出现

日志消息中的“状态”为 **JSON-RPC 语义**：成功显示 `OK`，单条错误显示错误码（如 `-32601`），batch 显示逗号分隔的每条结果（如 `OK, -32001`）；无 body（如 204 通知）也表示未报错，显示 `OK`。

日志消息格式示例：`JSON-RPC add → OK in 12.50ms`、`JSON-RPC get_user → -32001 in 5.00ms`、`JSON-RPC batch(2) [add, get] → OK, -32601 in 45ms`。

## 结构化日志（JSON）

便于 ELK、Loki 等采集与检索。两种常见方式：

### 方式一：配置 Python logging 的 Formatter

将根或 `wilrise` 的 Handler 设为输出 JSON 的 Formatter（例如 `python-json-logger` 或自定义），框架已有的 `extra` 会进入日志结构。

```python
import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "message": record.getMessage(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None),
            "rpc_methods": getattr(record, "rpc_methods", None),
            "status_code": getattr(record, "status_code", None),
            "rpc_codes": getattr(record, "rpc_codes", None),
            "duration_ms": getattr(record, "duration_ms", None),
        }
        return json.dumps(log)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.getLogger("wilrise").addHandler(handler)
logging.getLogger("wilrise").setLevel(logging.INFO)
```

### 方式二：自定义 RequestLogger

通过 `add_request_logger` 在每次请求完成时写入自己的结构化日志（或发送到日志服务）：

```python
from wilrise import Wilrise
from wilrise.context import RpcContext
from starlette.responses import Response
import logging
import json

def structured_request_logger(
    context: RpcContext,
    duration_ms: float,
    response: Response | None,
    error: BaseException | None,
) -> None:
    log = {
        "event": "rpc_request",
        "method": context.method,
        "request_id": context.request_id,
        "http_request_id": context.http_request_id,
        "duration_ms": round(duration_ms, 2),
        "status_code": response.status_code if response else None,
        "error": type(error).__name__ if error else None,
    }
    logging.getLogger("app.rpc").info(json.dumps(log))

app = Wilrise()
app.add_request_logger(structured_request_logger)
```

## 请求级 TraceId / SpanId

- 框架已将 HTTP 头 **`X-Request-ID`** 写入 `RpcContext.http_request_id`，并放入内置日志的 `extra`。
- 建议在网关或入口统一设置 `X-Request-ID`（及可选 `X-Trace-ID`），便于全链路关联。
- 在 `add_request_logger` 中可将 `context.http_request_id`、`context.method`、`duration_ms` 写入结构化日志或 OpenTelemetry Span，见下节。

## OpenTelemetry 集成（可选）

不强制框架依赖 OpenTelemetry；可在业务侧用 `add_request_logger` 或 middleware 创建 Span、记录 `rpc.method` 与 `duration_ms`，并随 `X-Trace-ID` 传播。

示例（需自行安装 `opentelemetry-api`、`opentelemetry-sdk` 等）：

```python
from opentelemetry import trace
from wilrise import Wilrise
from wilrise.context import RpcContext
from starlette.responses import Response

def otel_request_logger(
    context: RpcContext,
    duration_ms: float,
    response: Response | None,
    error: BaseException | None,
) -> None:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("rpc.method", context.method)
        span.set_attribute("http.request_id", context.http_request_id)
        span.set_attribute("rpc.duration_ms", duration_ms)
        if error:
            span.record_exception(error)

app = Wilrise()
app.add_request_logger(otel_request_logger)
```

在 ASGI 入口或上游 middleware 中创建 Span 并将 trace context 注入即可实现全链路追踪。

## Metrics（可选）

若有 Prometheus 等需求，可通过 `add_request_logger` 或 `add_after_call_hook` 统计请求数、延迟分位、按 method 与 status/code 的计数，再暴露给公司监控系统。示例仅给出思路：

```python
from wilrise import Wilrise
from wilrise.context import RpcContext
from starlette.responses import Response

# 伪代码：按实际使用的 metrics 库实现
def metrics_request_logger(
    context: RpcContext,
    duration_ms: float,
    response: Response | None,
    error: BaseException | None,
) -> None:
    # metrics.histogram("rpc_duration_seconds", duration_ms / 1000, labels={"method": context.method})
    # metrics.counter("rpc_requests_total", labels={"method": context.method, "status": response.status_code if response else "error"})
    pass

app = Wilrise()
app.add_request_logger(metrics_request_logger)
```

---

更多配置见 [Configuration](configuration.md)，错误与排查见 [Runbook](runbook.md)。
