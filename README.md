# LocalDeck MVP

LocalDeck 是一个独立的、无需 Docker 的本地 PowerPoint 生成 MVP。它接受纯文本主题，调用 GLM 完成“内容研究 → 页面设计”两个 Agent 阶段，在本机用 Playwright 检查 HTML，再用 PptxGenJS 导出并回读验证可编辑的 `.pptx`。

> 结论：当前 DeepPresenter 主运行链把浏览器、文件工具和转换环境放进 Docker，Docker 是其正常运行依赖，不只是开发依赖。LocalDeck 没有尝试假装容器不存在，而是把容器承担的隔离职责逐项替换成本地边界，因此核心流程可以不启动 Docker 复刻。

## 核心流程

```text
文本主题
  → CLI 参数校验
  → Research Agent ↔ GLM ↔ 本地 MCP
  → manuscript.md
  → Design Agent ↔ GLM ↔ 本地 MCP
  → slide_XX.html + global.css
  → Playwright 逐页检查
  → DOM 几何抽取
  → PptxGenJS 可编辑元素
  → python-pptx 回读验证
  → 原子发布 output.pptx
```

可交互调用链见 [`docs/call-chain.html`](docs/call-chain.html)。它支持深浅色、路径聚焦、缩放和导出。

## 原理拆解

### 1. Agent 不是“直接写 PPTX”

模型只负责决定下一步工具调用。通用 Agent Loop 把 system prompt、用户任务、工具定义和工具结果组成有界对话：

1. GLM 返回结构化 `tool_calls`。
2. Runtime 校验 JSON 参数并调用允许的本地 MCP 工具。
3. 工具结果作为 `tool` 消息回填给模型。
4. 模型继续修改文件或检查页面。
5. 只有 `finalize` 成功且本轮没有其他工具错误时，阶段才结束。
6. 超过最大轮次仍未完成则明确失败。

这使模型不能直接启动命令、浏览任意磁盘或绕过阶段验收。

### 2. Research 与 Design 分开

- **Research Agent** 把主题整理成严格页数的 Markdown，并以 `---` 分页。
- **Design Agent** 读取讲稿，生成一个全局 CSS 和严格编号的完整 HTML 页面。

分阶段的价值是把“内容是否完整”和“页面是否可用”分开校验。讲稿、HTML、截图和错误报告都会保留，失败后无需从零排查。

### 3. MCP 是工具协议，不等于远程服务

三个 MCP Server 都是当前机器上的 Python stdio 子进程：

- `workspace_server`：受限的读、写、编辑、移动、建目录和列目录。
- `quality_server`：启动本机 Playwright Chromium 检查页面。
- `task_server`：校验产物存在后才接受 `finalize`。

`LocalToolHub` 合并三个工具目录，再按阶段过滤可见工具。Research 看不到浏览器检查工具；两个阶段都看不到 Shell。

### 4. Docker 的职责如何被本地替换

| 原容器职责 | LocalDeck 替代 | 边界 |
| --- | --- | --- |
| 隔离文件系统 | `WorkspaceGuard` | 所有解析后路径必须仍在单次运行目录内 |
| 固定浏览器环境 | 本机 Playwright Chromium | 只加载工作区 HTML，固定视口 |
| 容器内命令执行 | 白名单 MCP 工具 | 模型没有 Shell 工具 |
| HTML 转 PPTX | 固定 Node 渲染器 | 仅 Pipeline 用固定参数启动 |
| 临时产物管理 | 每次运行独立目录 | 保留 manifest、历史、截图和报告 |

这不是与容器同等级的操作系统隔离；它是适合单用户本机 MVP 的应用层隔离。不要把它当作多租户执行沙箱。

### 5. HTML 为什么还能得到可编辑 PPTX

浏览器负责计算 CSS 最终布局。Exporter 从 DOM 中抽取文本、色块、边框和图片的最终像素几何与样式，再按页面比例映射到英寸坐标。Node 渲染器调用 PptxGenJS 创建真正的 PowerPoint 文本框、形状和图片，而不是把整页截图贴进 PPTX。

当前可编辑映射覆盖：

- `h1`–`h6`、`p`、`li`、`span` 文本；
- `div`、`section`、`header`、`footer`、`aside` 的背景、边框和圆角；
- 已成功加载的本地或 data URI 图片；
- 颜色、字号、字体、粗斜体、对齐、透明度和基础行高。

复杂 CSS 特效、SVG 动画、视频、图表语义和 PowerPoint 动画不在 MVP 范围内。

### 6. 两道质量门禁

HTML 门禁检查：

- 页面尺寸和整体滚动溢出；
- 元素是否越过页面边界；
- 文本是否被 `scrollWidth/scrollHeight` 裁切；
- 图片加载、浏览器控制台和页面错误。

PPTX 门禁检查：

- 文件可由 `python-pptx` 重新打开；
- 页数与请求一致；
- 每页至少包含一个非空、可编辑的文本形状。

导出先写临时文件，验证通过后才原子替换目标路径，避免失败时破坏已有文件。

## 环境要求

- Python 3.11 或更高版本；
- [`uv`](https://docs.astral.sh/uv/)；
- Node.js 20 或更高版本及 npm；
- 可访问 GLM OpenAI 兼容 API 的网络；
- PowerShell、bash 或其他普通终端。

不需要 Docker、WSL、LibreOffice 或 Poppler。

## 安装

在项目根目录执行：

```powershell
uv sync --extra dev
npm install --prefix localdeck/vendor/html2pptx
uv run playwright install chromium
```

Linux/macOS 使用同样三条命令。

## 配置密钥

密钥只从当前进程环境变量读取，不读取或生成包含真实密钥的配置文件。

PowerShell：

```powershell
$env:ZAI_API_KEY="替换成你自己的密钥"
```

bash/zsh：

```bash
export ZAI_API_KEY="替换成你自己的密钥"
```

可选变量：

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `LOCALDECK_MODEL` | `glm-5.2` | 模型名 |
| `LOCALDECK_BASE_URL` | `https://open.bigmodel.cn/api/coding/paas/v4` | Coding Plan 的 OpenAI Chat Completion 端点 |
| `LOCALDECK_RUNS_DIR` | `./runs` | 诊断工作区根目录 |

不要把真实密钥写入 `.env`、命令历史、Issue、截图或 Git；已经在聊天或其他外部位置暴露过的密钥应在服务端轮换。

## 生成 PPTX

```powershell
uv run localdeck generate "人工智能如何改变软件开发" `
  --slides 6 `
  --language zh `
  --aspect-ratio 16:9 `
  --output .\output.pptx
```

也可通过模块入口运行：

```powershell
uv run python -m localdeck generate "一个两页的测试主题" --slides 2 --output .\demo.pptx
```

当前参数：

- `topic`：必填文本主题或简报；
- `--slides / -n`：页数，默认 6；
- `--language`：`zh` 或 `en`；
- `--aspect-ratio`：`16:9` 或 `4:3`；
- `--output / -o`：必须以 `.pptx` 结尾。

## 运行产物

每次调用创建独立目录：

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

`manifest.json` 记录 Research、Design、Export、Verify 四个阶段的状态和产物。任何阶段失败，目录仍保留用于复盘。

## 测试与检查

PowerShell：

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
$env:TMP=(Resolve-Path .tmp)
$env:TEMP=$env:TMP
uv run python -m pytest -m "not live"
uv run ruff check .
uv run pyright localdeck
```

真实 API smoke test 默认跳过。明确设置 `LOCALDECK_RUN_LIVE_TESTS=1` 后才会使用当前环境中的 `ZAI_API_KEY`：

```powershell
$env:LOCALDECK_RUN_LIVE_TESTS="1"
uv run python -m pytest -m live tests/smoke/test_glm_live.py -v
```

## 安全边界

- `SecretStr` 防止密钥出现在配置 repr 或 JSON 序列化中。
- MCP 子进程环境会主动删除 `ZAI_API_KEY`。
- `WorkspaceGuard` 在规范化和解析符号链接后检查目录边界。
- 模型没有任意命令执行、网络抓取或宿主目录浏览工具。
- Node 和 Chromium 只由可信 Pipeline 以固定参数启动。
- 运行历史记录工具参数和结果，因此主题与生成内容不是私密日志。

## 已知限制

- MVP 只接受文本主题，不处理 PDF、DOCX、模板、网页研究或图片生成。
- 版式质量依赖模型；自动检查擅长发现越界和裁切，不评价审美与事实准确性。
- HTML-to-PPTX 只覆盖明确列出的 CSS/DOM 子集。
- MCP、浏览器和 Node 都在用户权限下运行，不具备容器级内核隔离。
- 2026-09-03 的 `npm audit` 会报告 2 个 high：`pptxgenjs@4.0.1` 的传递依赖 `image-size@2.0.2` 在 ICNS/JXL/HEIF 解析上存在拒绝服务公告，当前上游最新版尚无修复版。文本主题 MVP 不向模型开放任意图片输入，但部署到不可信输入环境前必须重新评估或替换该依赖。

## 项目文档

- [`docs/proposal.md`](docs/proposal.md)：目标、范围和验收标准；
- [`docs/plans/2026-09-03-localdeck-design.md`](docs/plans/2026-09-03-localdeck-design.md)：详细设计；
- [`docs/plans/2026-09-03-localdeck-mvp.md`](docs/plans/2026-09-03-localdeck-mvp.md)：实施计划；
- [`docs/call-chain.html`](docs/call-chain.html)：交互式调用链；
- [`docs/call-chain.json`](docs/call-chain.json)：可重复生成的 Archify 源规范。

## 目录结构

```text
localdeck/
├── agents/       # 通用 Agent Loop、Research、Design
├── llm/          # GLM OpenAI 兼容客户端
├── mcp/          # 本地 MCP Client、Hub 与三个 Server
├── prompts/      # 阶段 prompt
├── rendering/    # 浏览器抽取、PPTX 导出和回读验证
├── tools/        # 工作区受限文件工具
└── vendor/       # 小型、可审计的 Node PPTX 渲染器
```

LocalDeck 与原 `PPTAgent` 仓库完全分离，适合继续迭代 Web UI、附件解析、图片工作流或模板系统，而不会改动原项目。
