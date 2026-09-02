# LocalDeck MVP Proposal

## 目标

在 Windows、macOS 或 Linux 宿主机上运行一个不依赖 Docker 的演示文稿生成系统。第一版接收文本主题，通过 GLM-5.2 驱动两阶段 Agent 流程，生成可编辑的 PPTX 文件。

核心闭环：

```text
文本主题 → Research Agent → Markdown 文稿 → Design Agent → HTML 幻灯片 → 本地校验 → PPTX
```

## 已选方案

采用“原架构本地平移”方案：保留 Agent Loop、MCP stdio、HTML/CSS 设计、Playwright 校验和 PptxGenJS 导出，只将 Docker sandbox 替换为受工作区约束的本地 Python MCP 服务。

该方案比直接使用 `python-pptx` 更接近 DeepPresenter 的自由排版能力，也比复用旧版 PPTAgent 模板系统更容易扩展。

## MVP 范围

包含：

- 文本主题、目标页数、语言、页面比例和输出路径。
- Research Agent 生成分页 Markdown 文稿。
- Design Agent 生成全局样式和逐页 HTML。
- 本地 MCP 文件工具及 `finalize` 工具。
- Playwright 页面检查、截图和转换兼容性检查。
- PptxGenJS 生成可编辑 PPTX。
- 运行清单、消息历史、工具历史和错误日志。
- CLI、自动测试和独立调用链 HTML。

不包含：

- PDF、DOCX 或其他附件。
- 网络搜索、图片搜索和图片生成。
- 多 Agent 并行与任务委派。
- 任意本地命令执行。
- Web UI、模板归纳、动画和高级图表。

## 安全原则

- API Key 只从 `ZAI_API_KEY` 环境变量读取。
- 日志、配置示例、测试快照和 Git 历史不得包含密钥。
- 模型只能访问单次运行工作区。
- 本地工具不向模型开放 Shell。
- HTML 转换由受信任的 Pipeline 直接启动，而不是由模型启动。

## 验收标准

- 不安装或启动 Docker 也能运行。
- 一条 CLI 命令可以从主题生成 PPTX。
- PPTX 能被 `python-pptx` 重新打开且页数正确。
- 常规文本、色块、边框和图片在 PowerPoint 中保持可编辑。
- HTML 越界、文本裁切和转换失败有明确报告。
- API、工具和导出失败不会破坏已有输出。
- 默认测试不依赖真实 API，真实 GLM 测试为显式 smoke test。

