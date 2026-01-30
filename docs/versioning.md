# 版本与向后兼容策略

本文档说明 wilrise 的版本号策略、CHANGELOG、弃用策略与升级指南。

## 语义化版本（SemVer）

wilrise 采用 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)（MAJOR.MINOR.PATCH）：

- **MAJOR**：不兼容的 API 或行为变更；升级可能需要修改调用方代码。
- **MINOR**：向后兼容的新功能；在相同 MAJOR 内升级通常无需改代码。
- **PATCH**：向后兼容的问题修复；仅修复 bug 或文档，不改变公开 API。

当前状态为 **Beta（0.1.x）**：在 1.0 之前可能有不兼容调整；1.0 起承诺在**同一 MAJOR 内**向后兼容，仅在 MAJOR 升级时可能引入不兼容变更。

## CHANGELOG

版本变更记录见仓库根目录 [CHANGELOG.md](../CHANGELOG.md)，按版本列出：新增、变更、废弃、移除、修复，便于评估升级影响。

## 弃用策略

- 废弃行为会先在某个 **MINOR** 中标记为 **deprecated**（文档说明 + 运行时 `warnings.warn`，若适用）。
- 在**下一个 MAJOR** 中才会移除该行为；废弃期建议至少一个 MINOR 周期。
- 在 CHANGELOG 中会明确写出替代方案与迁移步骤。

## 升级指南

在发布新 MAJOR 或重要 MINOR 时，会在 `docs/` 下提供升级说明（如 `docs/upgrade-1.0.md`），包括：从 x.y 升级到 x'.y' 的步骤、配置变更、废弃 API 的替换方式，以减少升级成本。

## 测试与兼容性

- CI 保留对当前支持的最低 Python 版本（见 `pyproject.toml` 中 `requires-python`）的测试。
- 依赖的 lower bound 在 `pyproject.toml` 中明确，避免依赖突然升级导致行为变化。
