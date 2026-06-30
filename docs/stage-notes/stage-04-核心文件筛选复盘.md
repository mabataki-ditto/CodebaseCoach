# 阶段 4：核心文件筛选和 mock 文档生成复盘

## 1. 本阶段目标

本阶段目标是跑通“仓库读取之后到文档展示之前”的完整 mock 分析链路：

- 后端实现核心文件筛选规则。
- 根据仓库目录和文件路径筛选 5 到 12 个核心文件。
- 限制单文件读取大小，并跳过二进制文件。
- 实现 `POST /api/agent/analyze/mock`。
- 不调用真实 AI，只生成 mock Markdown。
- 将生成结果保存到 `generated_docs/`。
- 前端工作台调用后端接口，展示真实目录树、核心文件、Agent 步骤、工具日志和 mock Markdown 文档。

本阶段不接入 OpenAI，不引入 LangChain、MCP、RAG，也不实现历史记录。

## 2. 实际完成内容

- 新增 `apps/server/app/schemas/agent.py`，定义 mock 分析请求、核心文件摘要、Agent Step、Tool Log、生成文档和接口响应模型。
- 实现 `apps/server/app/services/file_selector_service.py`，按基础文件、入口文件和核心目录规则筛选核心文件。
- 实现 `apps/server/app/services/doc_storage_service.py`，将 mock Markdown 保存到 `generated_docs/{owner}_{repo}_{timestamp}/`。
- 实现 `apps/server/app/agent/workflow.py`，编排 URL 解析、clone、文件树、基础文件、核心文件、mock 文档生成和保存流程。
- 更新 `apps/server/app/api/agent.py` 和 `apps/server/app/main.py`，注册 `POST /api/agent/analyze/mock`。
- 更新 `apps/server/app/core/config.py` 和 `apps/server/.env.example`，增加核心文件数量和单文件读取上限配置。
- 新增后端单元测试，覆盖核心文件筛选、目录过滤、内容截断和文档落盘。
- 新增 `apps/web/src/types/analysis.ts` 和 `apps/web/src/api/analysis.ts`，沉淀前后端响应契约和 API 调用。
- 重写 `apps/web/src/pages/WorkspacePage.vue`，由前端 mock 数据改为调用后端 mock 分析接口。
- 新增 `apps/web/src/types/markdown-it.d.ts`，为当前依赖补最小类型声明。
- 验证真实公开仓库 `modelcontextprotocol/typescript-sdk` 可完成 mock 分析，生成 12 个核心文件和 7 份 Markdown 文档。

## 3. 遇到的问题与解决方案

### 问题 1：如何筛选核心文件而不是读取整个仓库？

#### S - Situation 背景

第二阶段已经可以 clone 仓库并生成目录树，但第四阶段需要为后续 AI 分析准备上下文。如果直接读取整个仓库，会违反“不一次性读取所有文件内容”和“必须限制单文件大小”的约束。

#### T - Task 任务

需要在不调用 AI 的情况下，用确定性规则从仓库中筛选 5 到 12 个核心文件，并读取有限长度的内容摘要。

#### A - Action 行动

在 `file_selector_service.py` 中实现规则评分：优先根目录 `README.md`、`package.json`、`pyproject.toml`、`requirements.txt`、`tsconfig.json`；优先 `main`、`index`、`app`、`server` 等入口命名；优先 `src`、`app`、`core`、`agent`、`tools`、`services`、`api`、`routes` 等目录。读取前过滤 `.git`、`node_modules`、`dist`、`build`、`.venv`、`__pycache__`、`test` 等目录，并只处理文本扩展名文件。读取时按 `MAX_CORE_FILE_BYTES` 截断，若检测到空字节则跳过。

#### R - Result 结果

后端可以稳定返回最多 12 个核心文件摘要，单元测试覆盖了目录过滤、二进制跳过和内容截断。真实仓库验收中返回了 12 个核心文件，满足本阶段演示要求。

#### 技术细节

- 核心函数：`select_core_files(root, max_files, max_bytes)`。
- 配置项：`MAX_CORE_FILES=12`、`MAX_CORE_FILE_BYTES=12000`。
- 响应模型：`CoreFileSummary`，包含 `path`、`file_type`、`size`、`content_preview`、`truncated`、`reason`、`read_status`、`used_for_context`。
- 过滤目录包括 `.git`、`node_modules`、`dist`、`build`、`.venv`、`venv`、`__pycache__`、`test`、`tests`。

#### 面试表达

我没有把仓库所有文件都交给后续 AI，而是先做规则筛选。规则优先 README 和配置文件，再看入口文件和核心目录，这样能在 MVP 阶段用低成本获得高价值上下文。读取时还限制单文件大小并跳过二进制文件，避免响应体和后续上下文失控。

### 问题 2：根目录 README 被嵌套 README 排在后面

#### S - Situation 背景

第一次真实仓库验收时，`modelcontextprotocol/typescript-sdk` 中的 `examples/tools/README.md`、`packages/core/README.md` 因为叠加了“基础文件 + 核心目录”评分，排序压过了根目录 `README.md`。

#### T - Task 任务

需要保证根目录 README、package 等项目入口信息优先进入核心文件列表，同时仍保留嵌套核心目录文件的竞争能力。

#### A - Action 行动

调整 `file_selector_service.py` 的评分规则：根目录基础文件获得更高权重，嵌套基础文件仍保留基础文件权重但不能压过根目录入口文件。随后重新运行 `python -m unittest` 和 `python -m compileall app`。

#### R - Result 结果

单元测试继续通过，筛选规则更贴合产品设计中的“先读项目入口信息”目标。

#### 技术细节

- 修正位置：`_build_candidate()`。
- 调整逻辑：`score += 3000 if "/" not in lower_path else 2000`。
- 排序仍按分数、基础文件顺序、路径深度和路径名稳定排序。

#### 面试表达

真实仓库验证能发现 mock 数据看不到的问题。嵌套 README 虽然有价值，但根目录 README 才是项目入口，所以我给根目录基础文件单独提权。这个调整让规则更符合用户理解项目的路径。

### 问题 3：mock 文档生成如何不伪装成真实 AI？

#### S - Situation 背景

第四阶段要求生成 Markdown 文档并保存，但明确禁止真实 AI 调用、OpenAI 接入、LangChain、MCP 和 RAG。

#### T - Task 任务

需要让演示链路完整可跑，同时在接口、页面和文档内容中清楚区分 mock 生成与真实 AI 生成。

#### A - Action 行动

在 `workflow.py` 中实现 `_build_mock_markdown_documents()`，只基于已读取的基础文件和核心文件摘要拼接 7 份 Markdown。每份文档都标注“mock 生成器”“未调用真实 AI”。文档通过 `doc_storage_service.py` 保存到 `generated_docs/`，前端用 `mock AI` 标签展示。

#### R - Result 结果

无 API Key 时完整流程可演示。真实仓库验收生成了 `01-项目概览.md` 到 `07-可贡献PR方向.md` 共 7 份文档，并且文档内容没有宣称来自真实 AI。

#### 技术细节

- 接口：`POST /api/agent/analyze/mock`。
- 保存目录：`generated_docs/{owner}_{repo}_{timestamp}/`。
- 文档模型：`GeneratedDocument`，包含 `title`、`filename`、`path`、`content`。
- 当前没有写入 `history.json`，历史记录属于后续阶段。

#### 面试表达

我把 mock 生成做成完整链路，但不把它包装成真实 AI。这样产品可以在没有 API Key 时演示端到端流程，同时保持技术诚实。后续接入真实模型时，只需要替换生成环节，文档保存和前端展示可以复用。

### 问题 4：前端从静态 mock 切换到真实后端响应

#### S - Situation 背景

第三阶段工作台只消费前端本地 mock 数据。第四阶段要求前端展示真实目录树、后端筛选出的核心文件和后端生成的 mock Markdown。

#### T - Task 任务

需要在不重做复杂 UI 的前提下，稳定接入后端接口，并保留错误提示和等待态。

#### A - Action 行动

新增 `types/analysis.ts` 定义响应契约，新增 `api/analysis.ts` 封装 fetch。`WorkspacePage.vue` 调用 `analyzeRepoWithMock()`，将后端 `file_tree` 转为 Naive UI `TreeOption`，把 `core_files`、`agent_steps`、`tool_logs`、`documents` 分别渲染到原有四区布局中。接口错误通过 `n-alert` 和 `n-message` 展示。

#### R - Result 结果

`pnpm build` 通过。工作台可以从后端接口展示真实文件树、核心文件列表、Agent 步骤、工具日志和 mock Markdown 文档。

#### 技术细节

- API 文件：`apps/web/src/api/analysis.ts`。
- 类型文件：`apps/web/src/types/analysis.ts`。
- 页面文件：`apps/web/src/pages/WorkspacePage.vue`。
- Markdown 预览使用 `markdown-it` 渲染，禁用 HTML 输入，代码高亮使用 `highlight.js`。
- 因项目没有 `@types/markdown-it`，新增本地最小声明 `apps/web/src/types/markdown-it.d.ts`，没有引入新依赖。

#### 面试表达

我没有把接口字段随手写进页面，而是先沉淀 TypeScript 契约和 API 封装。页面只关心展示状态，后端响应结构变化时影响面更小。错误也通过结构化错误展示，不会让页面崩溃。

### 问题 5：GitHub clone 在沙箱网络下失败

#### S - Situation 背景

完整验收 `/api/agent/analyze/mock` 时，后端能启动并访问 `/health`，但 Git clone 公开仓库失败，错误为 `schannel: AcquireCredentialsHandle failed`。

#### T - Task 任务

需要确认这是网络/凭据链路问题还是代码错误，并验证 clone 失败时接口不会导致服务崩溃。

#### A - Action 行动

先在普通沙箱执行完整接口请求，接口返回结构化 `REPO_CLONE_FAILED`，证明错误处理链路生效。随后按权限规则申请联网执行同一验收命令，成功 clone 仓库并完成 mock 分析。

#### R - Result 结果

失败场景返回结构化错误；提升权限联网后完整流程通过，返回 12 个核心文件、7 份文档和 `generated_docs/...` 保存目录。

#### 技术细节

- 错误来自 `github_service.py` 中 `Repo.clone_from()`。
- 结构化错误码：`REPO_CLONE_FAILED`。
- 成功验收仓库：`https://github.com/modelcontextprotocol/typescript-sdk`。
- 成功响应包括 `core_files`、`documents`、`docs_dir`、`agent_steps`、`tool_logs`。

#### 面试表达

我把外部网络失败和应用逻辑失败区分开处理。普通沙箱下 clone 失败时，接口仍返回结构化错误而不是服务崩溃；获得网络权限后，同一接口完成端到端流程。这说明错误边界和主流程都被验证过。

## 4. 技术取舍

- 规则筛选优先于 AI 筛选：当前阶段不接入真实 AI，规则可测试、可解释、可稳定复现。
- 保存 Markdown 文件而不是只返回内存内容：符合产品设计的文档存储要求，也为后续文档页和历史记录阶段预留基础。
- mock 文档生成放在 Agent 工作流中编排：便于前端展示 Agent Steps 和 Tool Logs，同时不把业务逻辑写入 FastAPI 路由。
- 前端保留原有工作台布局，只替换数据来源：降低第三阶段 UI 的返工成本。
- 使用本地 `markdown-it` 类型声明而不是新增 `@types/markdown-it`：避免为一个最小类型缺口新增依赖。

## 5. 面试可讲点

- 为什么核心文件筛选不能直接读取整个仓库？
- 如何设计可解释、可测试的核心文件筛选规则？
- mock AI 和真实 AI 的边界如何在产品和代码里表达？
- 为什么生成文档必须落盘到 Markdown？
- 前端如何从 mock 数据平滑切换到真实后端响应？
- 外部 GitHub clone 失败时如何保证结构化错误和服务稳定？

## 6. 相关 ADR

- `docs/adr/008-核心文件筛选采用规则优先策略.md`
- `docs/adr/009-mock文档生成保存为Markdown.md`
