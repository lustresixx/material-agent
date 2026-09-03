# LocalDeck MVP Design

## 1. 架构

LocalDeck 保留 DeepPresenter 的三段式运行骨架：内容生成、视觉设计和导出。所有工具服务器均作为本机 stdio 子进程启动，不再检查 Docker daemon，也不再创建容器。

```text
CLI
 └─ Pipeline
     ├─ Workspace
     ├─ MCP Hub
     │   ├─ Workspace Server
     │   ├─ Quality Server
     │   └─ Task Server
     ├─ Research Agent ↔ GLM-5.2
     ├─ Design Agent ↔ GLM-5.2
     ├─ HTML Inspector ↔ Playwright Chromium
     ├─ HTML-to-PPTX Exporter ↔ Node.js/PptxGenJS
     └─ PPTX Verifier
```

### 1.1 Research 阶段

Research Agent 接收主题、页数和语言，生成由 `---` 分隔的 Markdown 文稿。Agent 必须调用 `write_file` 保存 `manuscript.md`，然后调用 `finalize` 返回该文件。

### 1.2 Design 阶段

Design Agent 读取文稿，创建 `slides/global.css` 和 `slides/slide_XX.html`。每张幻灯片写入后必须调用 `inspect_slide`；检查失败时，Agent 修改页面并重新检查。所有页面通过后，Agent 调用 `finalize` 返回 `slides` 目录。

### 1.3 Export 阶段

Pipeline 使用可信的 Node 子进程调用 vendored HTML-to-PPTX 转换器。转换器将 DOM 文本、块元素、图片、列表和基础样式映射到 PptxGenJS 元素。完成后，Python 使用 `python-pptx` 重新打开文件并检查页数与基本元素。

## 2. 模块边界

```text
localdeck/
├── cli.py                    # Typer 命令与用户输出
├── config.py                 # 环境变量和运行设置
├── models.py                 # Pydantic 边界模型
├── pipeline.py               # 阶段编排与工作区生命周期
├── logging.py                # 原子 JSON 与 JSONL 持久化
├── agents/
│   ├── base.py               # 通用工具调用循环
│   ├── research.py           # 文稿阶段
│   └── design.py             # HTML 阶段
├── llm/
│   └── glm.py                # OpenAI 兼容异步客户端
├── mcp/
│   ├── client.py             # stdio 会话管理
│   ├── workspace_server.py   # 受限文件工具
│   ├── quality_server.py     # 页面检查工具
│   └── task_server.py        # finalize 工具
└── rendering/
    ├── exporter.py           # Node 转换器进程边界
    └── verifier.py           # PPTX 结构验证
```

vendored 转换器放在 `localdeck/vendor/html2pptx/`，保持独立来源说明，不与业务逻辑混合。

## 3. 数据模型

- `Settings`：API Base URL、模型、超时、重试、最大轮次、运行根目录。
- `GenerationRequest`：主题、页数、语言、宽高比、输出路径。
- `AssistantResponse` / `ToolCall`：模型回复和结构化工具调用。
- `MCPToolResult`：工具结果文本和错误状态。
- `InspectionIssue`：错误代码、严重级别、元素和说明。
- `InspectionReport`：页面尺寸、问题列表、截图和是否通过。
- `RunManifest`：运行 ID、阶段状态、主要产物和失败原因。
- `GenerationResult`：最终 PPTX 和所有可诊断产物的路径。

所有外部输入、API 响应、工具参数和阶段结果都在边界处校验。内部代码使用明确类型，不传递无约束字典。

## 4. Agent 状态机

1. 构建 system 和初始 user 消息。
2. 使用工具定义调用 GLM。
3. 若模型返回 tool calls，则逐个验证并执行。
4. 将每个工具结果以 `tool` 消息追加到历史。
5. 若成功执行 `finalize`，验证结果路径并结束。
6. 若模型没有工具调用且没有完成，追加简短继续指令。
7. 达到最大轮次仍未完成时抛出 `AgentTurnLimitError`。

Research 默认最多 8 轮；Design 默认最多 20 轮。质检失败会消耗 Design
轮次，达到总轮次上限后终止。

## 5. 本地 MCP 与路径安全

Workspace Server 第一版暴露：

- `read_file`
- `write_file`
- `edit_file`
- `move_file`
- `create_directory`
- `list_directory`

`WorkspaceGuard` 对每个路径执行以下处理：

1. 相对路径以当前运行工作区为基准。
2. 规范化绝对路径并解析现有符号链接。
3. 使用 `Path.is_relative_to()` 验证结果仍在工作区中。
4. 拒绝路径逃逸、工作区外绝对路径和越界移动。

模型不拥有 `execute_command`。Node、Playwright 和 PPTX 转换只由 Pipeline 内部的固定参数子进程调用。

## 6. HTML 检查

Quality Server 通过 Playwright 加载本地 HTML，并收集：

- 页面加载错误和浏览器控制台错误。
- `body` 是否符合请求的固定尺寸。
- 文档是否出现整体滚动溢出。
- 可见元素的边界是否超出页面。
- 文本节点的 `scrollWidth/clientWidth` 与 `scrollHeight/clientHeight` 是否表明裁切。
- 本地图片资源是否加载成功。

每次检查保存 JSON 报告和 PNG 截图。合法装饰性重叠不会被自动判错；第一版不实现通用重叠检测。

## 7. GLM 接入

使用 `openai.AsyncOpenAI` 连接智谱的 OpenAI 兼容端点：

- 默认 Base URL：`https://open.bigmodel.cn/api/coding/paas/v4`
- 默认模型：`glm-5.2`
- API Key：`ZAI_API_KEY`
- `tool_choice`：`auto`

401/403 不重试；429、5xx 和网络超时使用指数退避，最多 3 次。日志只记录模型、耗时、Token 和请求 ID，不记录认证头或完整环境变量。

## 8. 错误和恢复

- 非法工具 JSON：返回带错误标记的工具消息，允许模型修正。
- 未知工具：返回明确错误，不终止整个进程。
- 路径越界：拒绝并记录安全事件。
- HTML 检查失败：Design Agent 在限制次数内修复。
- Node 转换失败：保留文稿、HTML、截图、检查报告和 stderr。
- PPTX 验证失败：先写临时文件，验证成功后再原子移动到用户输出路径。
- Ctrl+C：关闭 MCP 会话和浏览器，保留工作区。

## 9. 运行产物

```text
runs/<timestamp>-<id>/
├── request.json
├── manifest.json
├── manuscript.md
├── slides/
│   ├── global.css
│   └── slide_XX.html
├── inspections/
│   ├── slide_XX.json
│   └── slide_XX.png
├── history/
│   ├── research.jsonl
│   ├── design.jsonl
│   └── tools.jsonl
└── output.pptx
```

## 10. 测试策略

实现严格遵循 RED → GREEN → REFACTOR：

- `WorkspaceGuard` 路径解析和逃逸测试。
- 文件工具真实读写测试。
- MCP stdio 往返测试。
- Fake LLM 驱动的 Agent Loop 测试。
- `finalize` 状态转换和轮次上限测试。
- Playwright 越界与文本裁切测试。
- HTML-to-PPTX 集成测试。
- PPTX 页数和可重新打开测试。
- Fake LLM 端到端测试。
- 显式启用的真实 GLM smoke test。
- 工作区密钥泄漏扫描测试。

## 11. CLI 与安装

```powershell
uv sync
npm install --prefix localdeck/vendor/html2pptx
uv run playwright install chromium
$env:ZAI_API_KEY="<your-key>"
uv run localdeck generate "主题" --slides 6 --language zh --output output.pptx
```

运行不要求 Docker、WSL、LibreOffice 或 Poppler。

## 12. 调用链文档

`docs/call-chain.html` 使用 Archify 生成，包含总体架构、Research/Design
主链路、本地 MCP 关系、导出门禁和失败恢复分支。最终文件必须通过
showcase validation、delivery 和多桌面尺寸 visual-check。
