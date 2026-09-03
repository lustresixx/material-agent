# LocalDeck MVP

LocalDeck 是一个独立的、无需 Docker 的本地 PowerPoint 生成器。它既保留“一句话生成 PPT”的基础模式，也支持“结构化大纲 + 已导入 PPTX 模板”的双路线模式：一条路线直接复用模板源页和组件，另一条路线依据模板字体、配色和间距生成新 HTML 布局。两条路线共享同一份内容计划，最终输出两份可编辑 `.pptx` 和并排对比报告。

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

模板大纲模式的核心链路：

```text
大纲 JSON + 已导入 PPTX 模板
  → 模板全页扫描、预览和风格抽取
  → Coding Plan Search/Reader MCP 并发检索每个 section
  → 自动分页（每个 section 至少 1 页，总计不超过 30 页）
  → 共享 slide-plan / 文案 / 证据
  ├─ Route B：克隆源页、替换可编辑槽、必要时派生模板布局
  └─ Route C：2–4 页批量生成模板约束 HTML、定点修复、PPTX 导出
  → PowerPoint 最终渲染 + 内容/结构/视觉质量闸门
  → template-route.pptx + html-route.pptx + comparison.html
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

### 6. 三层质量门禁

HTML 门禁检查：

- 页面尺寸和整体滚动溢出；
- 元素是否越过页面边界；
- 文本是否被 `scrollWidth/scrollHeight` 裁切；
- 图片加载、浏览器控制台和页面错误。

最终 PPTX 门禁检查：

- 文件可由 `python-pptx` 重新打开；
- 页数与请求一致；
- 每页至少包含一个非空、可编辑的文本形状；
- 大纲章节覆盖、原始顺序、证据与底部来源；
- 30 页上限、空占位符、品牌标识、疑似裁切和低对比文字；
- 全套页面是否过度复用同一种布局轮廓；
- Windows 上由 Microsoft PowerPoint 渲染最终 PPTX，最终渲染而非 HTML 截图是发布依据。

导出先写临时文件，验证通过后才原子替换目标路径，避免失败时破坏已有文件。

## 环境要求

- Python 3.11 或更高版本；
- [`uv`](https://docs.astral.sh/uv/)；
- Node.js 20 或更高版本及 npm；
- 可访问 GLM OpenAI 兼容 API 的网络；
- Windows PowerShell；
- 模板导入和模板双路线模式需要本机安装桌面版 Microsoft PowerPoint。

不需要 Docker、WSL、LibreOffice 或 Poppler。一句话 HTML 模式不依赖 PowerPoint；模板模式当前只在 Windows + PowerPoint 上提供最终渲染验收。

## 安装

在项目根目录执行：

```powershell
uv sync --extra dev
npm install --prefix localdeck/vendor/html2pptx
uv run playwright install chromium
```

Linux/macOS 可运行基础 HTML 路线，但当前没有模板模式所需的最终 PPTX 预览后端。

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
| `LOCALDECK_TEMPLATE_DIR` | `./templates` | 已导入模板包目录 |
| `LOCALDECK_SEARCH_MCP_URL` | 智谱 Coding Plan Search MCP | 公共网页搜索端点 |
| `LOCALDECK_READER_MCP_URL` | 智谱 Coding Plan Reader MCP | 公共网页读取端点 |
| `LOCALDECK_HTML_BATCH_SIZE` | `3` | Route C 单次生成页数，范围 2–4 |
| `LOCALDECK_MAX_REPAIRS` | `2` | Route C 失败页最大定点修复次数 |

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

## 使用 PPTX 模板和大纲

先导入模板。导入会扫描全部源页、抽取字体/配色/间距、识别可替换区域，并用 PowerPoint 生成本地审计预览：

```powershell
uv run localdeck template import "C:\资料\华为教育模板.pptx" `
  --name huawei-education

uv run localdeck template inspect huawei-education
```

大纲格式如下；每个 chapter 可以自动扩展为多页，但任何 section 都不会被删除或打乱：

```json
{
  "title": "交流材料标题",
  "chapters": [
    {
      "chapter_title": "1. 第一章",
      "sections": ["1.1 第一节", "1.2 第二节"]
    }
  ]
}
```

仓库内置了 [`examples/huawei-tongji-outline.json`](examples/huawei-tongji-outline.json)。一键生成两条路线：

```powershell
uv run localdeck generate `
  --outline .\examples\huawei-tongji-outline.json `
  --template huawei-education `
  --routes template,html `
  --max-slides 30 `
  --output-dir .\output\huawei-tongji
```

`--template` 使用导入时的名称，不接受任意外部路径。只重跑失败路线时，把 `--routes` 改为 `template` 或 `html`；已成功发布的另一份 PPTX 不会被生成失败覆盖。

研究只访问公开网页。Search MCP 找候选资料，Reader MCP 读取正文；可见页脚保留短来源，完整 URL、访问时间和失败记录保存在运行目录。请求会消耗 Coding Plan 对应的模型/MCP 配额，具体可用量和限流由智谱账户与套餐决定；额度不足或限流会明确失败，不会静默伪造事实。

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

模板模式的发布目录为：

```text
output/<name>/
├── template-route.pptx
├── html-route.pptx
├── comparison.html
└── comparison_assets/
```

运行工作区还会保留 `research/`、`planning/slide-plan.json`、`planning/frame-map.json`、两条路线的中间文件、PowerPoint 最终预览、质量报告、阶段耗时和去敏后的 MCP 调用历史。

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

- 模板必须是可编辑 `.pptx`；受密码保护或损坏的文件会在导入阶段失败。
- 图表、SmartArt、OLE、视频、动画和宏可以随克隆页保留，但当前不会自动改写其内部数据或行为。
- Route B 只编辑已识别的文本/图片槽；无法安全识别的对象按品牌家具保留或不使用。
- Route C 可以在模板设计令牌内创造新布局，但不能保证复刻 PowerPoint 动画、母版逻辑或所有复杂 SVG/CSS 效果。
- 公共检索质量取决于可访问网页与账户配额；正式对外材料仍应由业务和法务复核事实、引用与授权。
- 自动检查擅长发现结构、裁切、空白渲染和低对比问题，不替代人工审美评审。
- HTML-to-PPTX 只覆盖明确列出的 CSS/DOM 子集。
- MCP、浏览器和 Node 都在用户权限下运行，不具备容器级内核隔离。
- 2026-09-03 的本地安装报告 3 个 high 级 npm 依赖告警；其中包含 `pptxgenjs@4.0.1` 的传递依赖 `image-size@2.0.2` 解析拒绝服务公告。不要使用 `npm audit fix --force` 盲目升级；部署到不可信输入环境前应重新审计和替换受影响依赖。

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
├── comparison/   # Route B/C 并排报告
├── generation/   # 模板组件路线与模板约束 HTML 路线
├── inputs/       # 大纲规范化与校验
├── llm/          # GLM OpenAI 兼容客户端
├── mcp/          # 本地 MCP Client、Hub 与三个 Server
├── planning/     # 自动分页、共享 slide plan 与文案
├── prompts/      # 阶段 prompt
├── quality/      # HTML、内容和最终 PPTX 闸门
├── research/     # 公共检索、网页读取、证据与素材
├── rendering/    # 浏览器抽取、PPTX 导出和回读验证
├── templates/    # PPTX 导入、扫描、克隆与模板包
├── tools/        # 工作区受限文件工具
└── vendor/       # 小型、可审计的 Node PPTX 渲染器
```

LocalDeck 与原 `PPTAgent` 仓库完全分离，适合继续迭代 Web UI、附件解析、图片工作流或模板系统，而不会改动原项目。
