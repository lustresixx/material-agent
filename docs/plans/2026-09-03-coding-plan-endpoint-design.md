# Coding Plan 默认端点设计

## 目标

将 LocalDeck 的默认 GLM Base URL 从普通按量端点改为 GLM Coding Plan 的
OpenAI Chat Completion 端点。

## 设计

- 默认值改为 `https://open.bigmodel.cn/api/coding/paas/v4`。
- `LOCALDECK_BASE_URL` 的现有覆盖行为保持不变。
- `GLMClient` 继续使用 `AsyncOpenAI.chat.completions.create()`，不切换到
  Anthropic Messages 或 OpenAI Responses 协议。
- 同步更新测试、`.env.example`、README 和已有详细设计中的默认值。

## 验收

- 未设置 `LOCALDECK_BASE_URL` 时加载 Coding Plan 端点。
- 显式设置 `LOCALDECK_BASE_URL` 时仍使用调用方提供的地址。
- 全部离线测试、Ruff 和 Pyright 通过。

