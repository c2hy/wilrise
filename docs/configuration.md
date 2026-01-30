# 配置管理

本文档说明如何通过构造函数或环境变量配置 wilrise，以及默认 / 开发 / 生产三档建议。

## Wilrise 构造函数参数

- **`debug`**（默认 `False`）：为 `True` 时错误响应包含完整异常信息。**生产环境务必为 False**。
- **`max_batch_size`**（默认 `50`）：单次 batch 最大请求数，超出返回 -32600。
- **`max_request_size`**（默认 `1024*1024`，即 1MB）：请求体最大字节数，**仅在有 `Content-Length` 时校验**；无该头时框架不限制 body 大小。需严格限制时请使用反向代理或自定义中间件。
- **`log_requests`**（默认 `True`）：为 `True` 时按 JSON-RPC 风格记录请求（方法、状态码、耗时）。
- **`logger`**（默认 `None`）：用于请求/错误日志的 Logger；为 `None` 时使用 `logging.getLogger("wilrise.core")`。传入自定义 logger 可单独配置级别与 Handler。
- **`log_level`**（默认 `None`）：若设置，会调用 `logger.setLevel(log_level)`，仅发出不低于该级别的日志（如生产环境设 `logging.WARNING` 只打错误）。

## 环境变量约定

建议从环境变量读取与环境相关的配置，便于部署时区分开发 / 预发 / 生产，且不把敏感信息写进代码。

- **`WILRISE_DEBUG`** 对应 `debug`，未设置时视为 `0`（False）。
- **`WILRISE_MAX_BATCH_SIZE`** 对应 `max_batch_size`，未设置时默认 `50`。
- **`WILRISE_MAX_REQUEST_SIZE`** 对应 `max_request_size`，未设置时默认 `1048576`（1MB）。
- **`WILRISE_LOG_REQUESTS`** 对应 `log_requests`，未设置时视为 `1`（True）。
- **`WILRISE_LOG_LEVEL`** 对应 `log_level`，未设置时不生效，使用 logger 默认级别。

框架不强制内置 dotenv；业务可自行用 `os.environ` 或 [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) 等读取。

**关于 max_request_size**：仅在请求带 `Content-Length` 头时才会检查 body 大小；客户端若不发该头则可绕过此限制。生产环境若需无论是否有该头都限制 body 大小，请在前置反向代理（如 Nginx）或自定义中间件中实现。

## 从环境变量构建 Wilrise（可选）

使用可选辅助函数 `from_env()` 可从环境变量生成配置 dict，再传给 `Wilrise(**from_env())`：

```python
from wilrise import Wilrise, from_env

# 从环境变量读取 WILRISE_*，未设置则用默认值。`WILRISE_LOG_LEVEL` 可为 DEBUG、INFO、WARNING、ERROR（大小写不敏感）。
app = Wilrise(**from_env())
```

`logger` 无法从环境变量构造，需在代码中传入（如 `Wilrise(**from_env(), logger=logging.getLogger("app.rpc"))`）。实现逻辑等价于：

```python
import os

def _from_env() -> dict:
    def _bool(key: str, default: bool) -> bool:
        v = os.environ.get(key)
        if v is None:
            return default
        return v.strip().lower() in ("1", "true", "yes")

    return {
        "debug": _bool("WILRISE_DEBUG", False),
        "max_batch_size": int(os.environ.get("WILRISE_MAX_BATCH_SIZE", "50")),
        "max_request_size": int(os.environ.get("WILRISE_MAX_REQUEST_SIZE", "1048576")),
        "log_requests": _bool("WILRISE_LOG_REQUESTS", True),
    }
```

## 三档配置示例

### 默认（不显式设置）

保持框架默认行为：`debug=False`、`log_requests=True`、`max_batch_size=50`、`max_request_size=1MB`。

### 开发

便于本地排查问题：

```python
app = Wilrise(debug=True, log_requests=True)
# 或从 env：WILRISE_DEBUG=1 uv run python main.py
```

### 生产

关闭 debug，按公司策略设置限制，并从环境变量注入：

```python
from wilrise import Wilrise, from_env

app = Wilrise(**from_env())
# 部署时设置：WILRISE_DEBUG=0 WILRISE_MAX_BATCH_SIZE=100 WILRISE_MAX_REQUEST_SIZE=2097152
```

或不用 `from_env`，自行从配置中心 / env 读取后传入：

```python
app = Wilrise(
    debug=False,
    max_batch_size=int(os.environ.get("WILRISE_MAX_BATCH_SIZE", "50")),
    max_request_size=int(os.environ.get("WILRISE_MAX_REQUEST_SIZE", str(1024 * 1024))),
    log_requests=True,
)
```

## 敏感信息不入代码

密钥、数据库 URL、JWT secret 等**必须**从环境变量或密钥管理服务读取；示例项目（如 `examples/auth_crud`）仅使用占位或 `os.environ.get("...")` 示例，不得提交真实密钥。详见 [CONTRIBUTING](../CONTRIBUTING.md#security) 中的 Security 小节。
