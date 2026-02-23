# 架构与扩展点

本文档简述 wilrise 的请求生命周期、Router/Use 机制与扩展点，便于二次开发与对接公司规范。

## 请求生命周期

1. **HTTP 入口**：仅接受 POST；非 POST 返回 405 与 Invalid Request。
2. **Body 与大小**：读取 JSON body；若带 `Content-Length` 且超过 `max_request_size`，返回 413。
3. **Batch 校验**：若 body 为数组，长度超过 `max_batch_size` 返回 400（-32600）；空数组返回 400。
4. **单条解析**：每条请求经 `RequestParser` 解析为 `ParsedRequest`（method、params、id、is_notification）。
5. **方法查找**：未注册方法返回 -32601（Method not found）。
6. **Before 钩子**：执行 `before_call_hooks`；若某钩子返回 error dict，直接响应该错误，不执行方法。
7. **参数解析与依赖注入**：根据方法签名解析 params、执行 `Use` 依赖；缺参或校验失败返回 -32602；依赖或业务抛出 `RpcError` 则按码返回；其它未映射异常经 `ExceptionMapper` 或最终 -32603。
8. **方法执行**：调用 RPC 方法。**同步方法**（`def`）在线程池中执行（`asyncio.to_thread`），与 FastAPI/Starlette 的同步端点行为一致，避免阻塞 I/O 拖慢事件循环；**异步方法**（`async def`）在事件循环中直接执行。`RpcError` 或 `ExceptionMapper` 映射同上；未映射异常返回 -32603。
9. **结果序列化**：结果需 JSON 可序列化，否则返回 -32603。
10. **After 钩子**：成功执行后执行 `after_call_hooks`。
11. **请求完成日志**：内置 `log_requests` 与所有 `add_request_logger` 的 RequestLogger 被调用（context、duration_ms、response、error）。
12. **Background tasks**：若有 `request.state.background_tasks`，在响应发送后 fire-and-forget 执行。

## Router 与 Use

- **Router**：通过 `@router.method` 注册方法，再通过 `app.include_router(router, prefix="...")` 挂到 app 上；最终 RPC 方法名为 `prefix + method_name`（如 `user.get`）。
- **Use**：依赖注入；参数默认值为 `Use(provider)` 时，框架会调用 `provider(request)`（支持 async），将返回值作为该参数传入；若 provider 抛异常，按 -32603 或 `ExceptionMapper` 处理。

## 扩展点

- **RequestParser**：自定义请求体解析（如非标准 JSON-RPC）。设置方式：`set_request_parser(parser)`。
- **ResponseBuilder**：自定义成功/错误响应结构。设置方式：`set_response_builder(builder)`。
- **ExceptionMapper**：将未捕获异常映射为 (code, message, data)。设置方式：`set_exception_mapper(mapper)`。
- **RequestLogger**：请求完成时打日志或上报（context、duration_ms、response、error）。设置方式：`add_request_logger(logger_fn)`。

Before/After 钩子：

- **BeforeCallHook**：`(method_name, params, request) -> error_dict | None`；返回 dict 则直接响应该错误。
- **AfterCallHook**：`(method_name, result, request) -> None`；仅成功执行后调用，用于审计、指标等。

详见 [wilrise.extensions](https://github.com/.../blob/main/wilrise/extensions.py) 与 [README - Configuration](../README.md#configuration)。
