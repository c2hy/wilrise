# 更新日志

本文件记录本项目的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

（暂无）

## [0.1.0] - 2025-01-30

首个公开发布。

### 新增

- JSON-RPC 2.0 服务（基于 Starlette，支持单条与批量请求）。
- `@app.method` / Router、`Use` 依赖注入、`Param`（description、alias）。
- 可选的 Pydantic 校验（参数与结果序列化）。
- 扩展点：RequestParser、ResponseBuilder、ExceptionMapper、RequestLogger。
- 调用前后钩子、启动/关闭、中间件、挂载到已有应用。
- 可选 `from_env()`：从 `WILRISE_*` 环境变量构建 `Wilrise` 的 kwargs。
- 文档：生产就绪相关（errors、configuration、observability、versioning、runbook、architecture）。

[未发布]: https://github.com/your-username/wilrise/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-username/wilrise/releases/tag/v0.1.0
