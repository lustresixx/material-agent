# 通用 OpenAI 协议接入设计

## 背景

LocalDeck 当前虽然通过 OpenAI Python SDK 调用模型，但配置和运行行为仍与
智谱 Coding Plan 强绑定：必须提供 `ZAI_API_KEY`、默认向每次请求附加智谱
`thinking` 参数，并把同一个模型密钥用于智谱 Search/Reader MCP。这样会导致
本地模型、兼容 OpenAI Chat Completions 的代理服务，以及不要求鉴权的服务无法
直接使用。

本次改动只抽象模型接入与研究模式，不改变 PPTX 生成、模板分析、双路线生成和
质量检查的核心流程。

## 目标

- 用户可以通过命令行或环境变量设置 OpenAI-compatible Base URL、模型和 Key。
- API Key 可以为空；空 Key 场景仍能初始化客户端并调用不鉴权的本地服务。
- 保持现有 GLM Coding Plan 配置可用，且仅在 Coding Plan 模式发送智谱专用参数。
- 模型 API 与联网研究凭据解耦，通用模型 Key 不会被发送给智谱 MCP。
- 模板大纲模式在没有 MCP 配置时自动使用模型扩写，不因缺少联网搜索而失败。
- 配置优先级明确：命令行参数高于新通用环境变量，高于旧兼容环境变量，高于默认值。

## 非目标

- 不实现 OpenAI Responses、Anthropic Messages 等其他协议。
- 不承诺所有 OpenAI-compatible 服务都支持工具调用；一句话 Agent 路线仍要求模型
  支持 Chat Completions tool calls。
- 不为通用模型虚构联网搜索能力，也不为无来源的模型扩写生成引用。
- 不移除 `ZAI_API_KEY`、`LOCALDECK_MODEL` 和 `LOCALDECK_BASE_URL` 等旧配置。

## 配置模型

### 模型提供方

新增 `provider`：

- `openai`：纯 OpenAI Chat Completions 兼容模式，不发送厂商扩展字段。
- `coding-plan`：调用 GLM Coding Plan，并发送
  `extra_body={"thinking": {"type": "enabled"}}`。

如果用户没有显式设置 provider，则根据最终 Base URL 判断：主机为
`open.bigmodel.cn` 且路径包含 `/coding/` 时使用 `coding-plan`，其余地址使用
`openai`。这使现有命令保持原行为，也让自定义地址默认走最通用的请求格式。

### 环境变量与优先级

模型配置使用以下优先级：

1. CLI：`--base-url`、`--api-key`、`--model`、`--provider`。
2. 通用环境变量：`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`、
   `LOCALDECK_PROVIDER`。
3. 旧环境变量：`LOCALDECK_BASE_URL`、`ZAI_API_KEY`、`LOCALDECK_MODEL`。
4. 现有 Coding Plan 默认 Base URL 与模型。

显式设置为空字符串的 `OPENAI_API_KEY` 或 `--api-key ""` 是有效配置，并会覆盖
旧的 `ZAI_API_KEY`。Base URL 和模型不能为空，若为空则在执行网络请求前给出明确的
配置错误。

OpenAI Python SDK 要求构造时提供非空 `api_key`。对于用户配置的空 Key，网络边界
会使用固定的非敏感占位值 `not-required`。它不会被保存到运行产物，也不代表真实
凭据；多数无需鉴权的本地兼容服务会忽略该 Authorization 值。

### 研究配置

新增 `research_mode`：

- `auto`（默认）：MCP 配置完整时联网研究，否则使用模型扩写。
- `mcp`：强制使用 Search/Reader MCP；缺少配置时立即报错。
- `llm`：只使用当前模型扩写大纲，不访问外网。
- `off`：不扩写，只依据用户大纲生成基础内容。

新增独立的 `LOCALDECK_MCP_API_KEY`。为了兼容现有用户，如果该变量未设置，
`ZAI_API_KEY` 可继续作为智谱 MCP Key；`OPENAI_API_KEY` 永远不会被隐式复用为
MCP Key。现有 `LOCALDECK_SEARCH_MCP_URL` 和 `LOCALDECK_READER_MCP_URL` 保留。

CLI 新增 `--research-mode auto|mcp|llm|off`。联网研究地址和 MCP Key 暂时保持为
环境变量，避免在命令历史里暴露额外凭据。

## 运行流程

```text
CLI 参数
   ↓ 覆盖
OPENAI_* / LOCALDECK_PROVIDER
   ↓ 回退
LOCALDECK_* / ZAI_API_KEY
   ↓
Settings（校验 URL、模型、provider、research_mode）
   ├─ OpenAI-compatible LLM client
   │    ├─ openai: 标准 Chat Completions
   │    └─ coding-plan: 标准请求 + GLM thinking 扩展
   └─ 模板路线 research stage
        ├─ mcp: Search MCP → Reader MCP → 有来源 ResearchPacket
        ├─ llm: 模型扩写 → 无引用 ResearchPacket
        ├─ off: 大纲占位 ResearchPacket
        └─ auto: MCP 可用则 mcp，否则 llm
```

模型扩写模式用一次批量请求为全部 section 生成结构化 JSON，得到若干适合演示
文稿的核心观点，避免逐节请求造成额外等待。
这些观点没有外部证据，因此 `evidence_ids` 与来源页脚保持为空。解析结果不合格时，
对应 section 降级为大纲原文，保证一键生成可以继续完成。`ResearchClaim` 将允许空
`evidence_ids`，其含义明确限定为“模型生成但未经外部来源验证”；联网研究生成的
claim 仍必须携带实际 evidence ID。

## 代码结构

- `localdeck/config.py`
  - 增加 provider/research mode 枚举、环境变量优先级、CLI override 方法和校验。
- `localdeck/cli.py`
  - 增加模型与研究模式选项，把 CLI override 合并进环境配置。
- `localdeck/llm/glm.py`
  - 抽象为通用 OpenAI-compatible 客户端，同时保留 `GLMClient` 兼容名称。
  - 空 Key 在 SDK 边界替换为占位值；仅 Coding Plan 模式附加 `thinking`。
- `localdeck/research/llm.py`
  - 批量扩写结构化大纲，并把结果转成无外部引用的 `ResearchPacket`。
- `localdeck/research/models.py`
  - 允许模型扩写 claim 的 evidence ID 为空。
- `localdeck/pipeline.py`
  - 根据研究模式选择 MCP、LLM 或 outline-only 路线。
- `.env.example`、`README.md`
  - 记录通用配置、兼容配置、空 Key 和研究模式示例。

## 错误与降级

- Base URL、model、provider 或 research mode 无效：CLI 返回配置错误和退出码 2。
- `research_mode=mcp` 但 MCP URL/Key 不完整：在创建网络客户端前返回配置错误。
- `research_mode=auto` 且 MCP 不完整：使用 LLM 扩写，不视为异常。
- LLM 扩写返回非 JSON 或不完整 JSON：保留可验证部分，其余 section 使用原标题。
- 一句话 Agent 路线中模型不支持 tool calls：保留现有生成失败语义，并在文档中说明
  该路线的能力要求。

## 安全边界

- 模型 Key 和 MCP Key 都使用 `SecretStr`，不进入 repr、JSON 配置产物或日志。
- 通用 `OPENAI_API_KEY` 不会自动传给 MCP 服务。
- CLI 支持 `--api-key` 是用户明确要求；文档优先推荐环境变量，避免 shell 历史泄露。
- 空 Key 占位值是常量，不含用户数据。

## 向后兼容

以下原命令无需修改：

```powershell
$env:ZAI_API_KEY="..."
uv run localdeck generate --outline .\outline.json --template huawei
```

它仍会使用 Coding Plan 模型端点，并在 `auto` 模式下复用 `ZAI_API_KEY` 调用智谱
Search/Reader MCP。原有 `LOCALDECK_MODEL`、`LOCALDECK_BASE_URL` 覆盖继续生效。

通用本地服务示例：

```powershell
uv run localdeck generate --outline .\outline.json --template huawei `
  --base-url http://127.0.0.1:8000/v1 --model qwen3 `
  --api-key "" --research-mode llm
```

## 测试与验收

- 单元测试覆盖所有配置优先级，包括“显式空 Key 覆盖旧 Key”。
- 单元测试确认通用请求没有智谱扩展字段，Coding Plan 请求仍带 `thinking`。
- CLI 测试确认四个参数能覆盖环境配置，并安全接受空 Key。
- 研究测试覆盖 `auto` 选择逻辑、MCP 强制校验、LLM JSON 解析和 outline-only 降级。
- 现有离线测试、Ruff、Pyright 全部通过。
- 使用本地假 OpenAI-compatible HTTP 服务做一次无 Key 冒烟测试，确认请求可到达并
  生成预期中间产物；真实 PPTX 端到端仍取决于模型是否支持对应路线所需能力。
