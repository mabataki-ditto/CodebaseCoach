# 阶段 1：项目骨架复盘

## 1. 本阶段目标

本阶段目标是完成 CodebaseCoach 的项目基础结构和前后端骨架：

- 创建符合规划的项目目录结构。
- 建立 Vue 3 + TypeScript + Vite 前端项目。
- 接入 Naive UI。
- 建立 Python + FastAPI 后端项目。
- 建立前后端基础启动命令。
- 创建首页、分析工作台、文档页、历史记录页、设置页页面骨架。
- 创建 FastAPI `/health` 接口。
- 创建 `.env.example`。
- 创建 `generated_docs/`、`temp_repos/`、`data/` 目录。
- 创建基础 README。

本阶段明确不实现真实 AI 调用、不实现 GitHub clone、不引入 LangChain、MCP、RAG，不把 API Key 写死进代码。

## 2. 实际完成内容

- 创建 `apps/web` 前端工程，使用 Vue 3、TypeScript、Vite、Vue Router、Pinia 和 Naive UI。
- 创建 `apps/web/src/pages/` 下的五个页面骨架：`HomePage.vue`、`WorkspacePage.vue`、`DocsPage.vue`、`HistoryPage.vue`、`SettingsPage.vue`。
- 在首页实现 GitHub 仓库 URL 的前端基础校验和工作台跳转。
- 在分析工作台骨架中展示仓库信息、文件树、核心文件、Agent 步骤、工具调用日志和 Markdown 预览占位。
- 创建 `apps/server` FastAPI 后端工程。
- 创建 `GET /health` 接口，返回服务状态、服务名和版本。
- 创建后端分层目录：`api`、`schemas`、`services`、`agent`、`core`、`utils`。
- 创建 `apps/server/.env.example`，只提供环境变量示例，不包含真实密钥。
- 创建根目录 `README.md`、`.gitignore`、`pnpm-workspace.yaml`。
- 创建运行数据目录：`generated_docs/`、`temp_repos/`、`data/`，并用 `.gitkeep` 保留空目录。
- 将原始产品与开发提示词复制到 `docs/`，并新增本阶段复盘和 ADR 文档。

## 3. 遇到的问题与解决方案

### 问题 1：为什么项目采用前后端分离结构？

#### S - Situation 背景

CodebaseCoach 后续会同时涉及浏览器交互、仓库文件读取、临时目录管理、Markdown 文档落盘、OpenAI API Key 读取和 AI 调用封装。如果把这些能力混在一个前端应用或单体脚本里，职责边界会变得模糊，安全边界也不清楚。

#### T - Task 任务

第一阶段需要搭建可运行骨架，同时保证后续仓库读取、AI 调用和文档保存都能放在服务端，不让前端直接接触 API Key 或本地文件系统能力。

#### A - Action 行动

采用 `apps/web` 与 `apps/server` 的前后端分离结构。前端负责页面路由、输入、状态展示和用户交互；后端负责 FastAPI 应用入口、CORS 配置、环境变量读取和 `/health` 接口。根目录保留 `generated_docs/`、`temp_repos/`、`data/`，为后续服务端运行数据留出位置。

#### R - Result 结果

前端和后端可以独立安装、启动和构建。浏览器端不会保存或展示完整 API Key，后续仓库 clone、文件扫描、AI 调用、Markdown 保存都能在后端服务中逐步实现。

#### 技术细节

- 前端入口：`apps/web/src/main.ts`。
- 后端入口：`apps/server/app/main.py`。
- 前端默认开发地址：`http://localhost:5173`。
- 后端默认开发地址：`http://localhost:8000`。
- CORS 来源通过 `apps/server/app/core/config.py` 中的 `BACKEND_CORS_ORIGINS` 配置。

#### 面试表达

这个项目采用前后端分离，是因为前端只应该处理交互和展示，仓库读取、文件落盘和 AI 调用都属于服务端能力。这样可以避免 API Key 暴露到浏览器，也能让分析流程通过后端 API 稳定沉淀。第一阶段先把两端启动链路打通，后续再逐步补仓库分析和文档生成。

### 问题 2：Vue 3 + TypeScript + Naive UI 在本项目中分别承担什么角色？

#### S - Situation 背景

本项目不是聊天页，而是一个结构化工作台。前端需要展示首页入口、仓库信息、文件树、Agent 步骤、工具日志、Markdown 预览、历史记录和设置说明。

#### T - Task 任务

第一阶段需要用指定技术栈搭出能启动、能构建、能路由切换的页面骨架，并证明 Naive UI 已经正确接入。

#### A - Action 行动

使用 Vue 3 组织组件和响应式状态，使用 TypeScript 约束组件状态与后续接口数据结构，使用 Vite 提供开发和构建能力，使用 Naive UI 搭建布局、卡片、输入框、按钮、树、步骤条、标签、Tabs、时间线和消息提示。

#### R - Result 结果

前端已经能在五个页面之间切换。首页提供 GitHub URL 输入和校验，工作台展示文件树、Agent 步骤和 Markdown 预览的产品核心结构，文档页、历史记录页和设置页都有第一阶段骨架。

#### 技术细节

- Vue 应用创建在 `apps/web/src/main.ts`。
- 路由定义在 `apps/web/src/router/index.ts`。
- Naive UI Provider 接入在 `apps/web/src/App.vue`。
- 页面文件位于 `apps/web/src/pages/`。
- `apps/web/src/styles.css` 定义基础布局和浅色工作台样式。

#### 面试表达

Vue 3 在项目中负责组件化和响应式交互，TypeScript 负责约束后续 API 数据和页面状态，Naive UI 负责提供一致的工作台组件。这个组合能快速做出可运行 MVP，同时避免一开始自研设计系统。第一阶段只做页面骨架，后续再把真实仓库分析数据接入这些组件。

### 问题 3：FastAPI 后端骨架为什么要单独拆分目录，而不是都写在 `main.py`？

#### S - Situation 背景

后端后续会包含 GitHub URL 解析、仓库 clone、文件树生成、核心文件筛选、Prompt 构建、AI 调用、文档保存、历史记录保存和结构化错误返回。即使第一阶段只有 `/health`，后续业务复杂度也不会停留在单文件级别。

#### T - Task 任务

需要让后端第一阶段保持可运行，同时避免把未来的业务逻辑都塞进 `main.py`。

#### A - Action 行动

将 `apps/server/app/main.py` 限定为应用组装入口，只负责创建 FastAPI app、配置 CORS、注册 router。将健康检查路由放到 `app/api/health.py`，响应模型放到 `app/schemas/health.py`，配置读取放到 `app/core/config.py`，未来业务能力按目录预留在 `services` 和 `agent` 中。

#### R - Result 结果

`main.py` 保持很薄，`GET /health` 已可访问。后续新增 repo、agent、docs、history 接口时，可以继续按 `api -> schema -> service` 的边界补充，不需要重构入口文件。

#### 技术细节

- `create_app()` 位于 `apps/server/app/main.py`。
- `/health` 路由位于 `apps/server/app/api/health.py`。
- `HealthResponse` 位于 `apps/server/app/schemas/health.py`。
- `Settings` 位于 `apps/server/app/core/config.py`。
- 空的 `repo.py`、`agent.py`、`docs.py`、`history.py` 当前只作为后续路由文件占位，不代表已实现接口。

#### 面试表达

我把 FastAPI 拆成分层目录，是为了防止入口文件变成业务堆叠。`main.py` 只做应用组装，API 层处理请求响应，schema 层定义数据结构，service 层承载业务能力，agent 层承载工作流和 Prompt。第一阶段只实现健康检查，但先把边界放对，后续扩展更稳。

### 问题 4：当前阶段有没有为了后续 Agent、AI 调用、MCP 扩展预留结构？

#### S - Situation 背景

产品设计中后续会有可控工作流 Agent、AI 文档生成、工具调用日志，MCP 和 RAG 也被列为 MVP 之后的扩展方向。但第一阶段明确禁止实现真实 AI 调用、GitHub clone、LangChain、MCP 和 RAG。

#### T - Task 任务

需要在不跨阶段实现复杂功能的前提下，为后续 Agent、Prompt、工具调用、LLM 封装和运行数据保存留出合理位置。

#### A - Action 行动

只创建轻量结构，不写真实业务逻辑：`app/agent/workflow.py`、`app/agent/tools.py`、`app/agent/prompts.py` 作为后续工作流与 Prompt 位置；`app/services/llm_service.py` 作为后续 AI 调用统一封装位置；`generated_docs/`、`temp_repos/`、`data/` 作为后续文档、临时仓库和本地数据目录。

#### R - Result 结果

当前项目具备后续扩展落点，但运行时仍然只是第一阶段骨架。代码中没有 LangChain、MCP、RAG 依赖，也没有把 mock 或占位内容描述成真实 AI 能力。

#### 技术细节

- Agent 预留目录：`apps/server/app/agent/`。
- AI 调用预留文件：`apps/server/app/services/llm_service.py`。
- 文档输出目录：`generated_docs/`。
- 临时仓库目录：`temp_repos/`。
- 本地数据目录：`data/`。
- 当前没有实现 `run_codebase_analysis_workflow`，也没有实现 OpenAI SDK 调用。

#### 面试表达

我在第一阶段只预留 Agent 和 AI 的目录边界，没有提前实现复杂工作流。这样既能让后续 Prompt、工具调用和 LLM 封装有明确位置，又不会把 MVP 骨架做复杂。MCP 和 RAG 只是后续扩展方向，当前没有进入运行时代码。

### 问题 5：依赖安装和启动验证为什么没有直接使用系统默认命令？

#### S - Situation 背景

本地环境中 `pnpm` 和 `python` 不在系统 PATH 中，`npm` 的 PowerShell 脚本受到执行策略限制。后端直接用全局 pip 安装依赖时，还遇到用户目录写入权限问题。

#### T - Task 任务

需要完成阶段验收中的 `pnpm install`、`pnpm dev`、`pnpm build`、`pip install -r requirements.txt`、`uvicorn app.main:app --reload --port 8000` 和 `/health` 访问验证，同时不把依赖安装到不可控的全局位置。

#### A - Action 行动

前端通过 Corepack 提供 pnpm，并在根目录创建 `pnpm-workspace.yaml`，允许 Vite 所需的 `esbuild` 执行构建脚本。后端使用 Codex 提供的 Python 创建 `apps/server/.venv` 虚拟环境，再在虚拟环境中安装 `requirements.txt`。服务启动用临时进程验证，不留下不可控的常驻后台进程。

#### R - Result 结果

前端依赖安装、`pnpm build`、`pnpm dev` 临时访问验证均通过。后端虚拟环境安装、`python -m compileall app`、Uvicorn 临时启动和 `/health` 访问验证均通过。

#### 技术细节

- 根目录 `pnpm-workspace.yaml` 配置 `apps/web` 工作区和 `onlyBuiltDependencies: esbuild`。
- 前端锁文件保留在根目录 `pnpm-lock.yaml`。
- 后端虚拟环境位于 `apps/server/.venv`，被 `.gitignore` 忽略。
- `/health` 验证返回 `{"status":"ok","service":"codebase-coach-server","version":"0.1.0"}`。

#### 面试表达

这次环境问题不是业务 bug，而是本地工具链约束。我的处理方式是避免污染全局环境：前端用 Corepack 管理 pnpm，后端用项目虚拟环境安装依赖。这样既能完成验收，也能保证后续开发者按项目目录复现。

## 4. 技术取舍

- 采用前后端分离，而不是纯前端或单体应用：牺牲一点启动复杂度，换取清晰安全边界和后续服务端能力承载位置。
- 前端采用 Vue 3 + TypeScript + Vite + Naive UI，而不是 Nuxt、Element Plus 或 shadcn-vue：符合指定技术栈，能快速搭建结构化工作台，同时避免 SSR 或额外 UI 框架复杂度。
- 后端采用 FastAPI 分层骨架，而不是单文件 `main.py`：当前文件更多，但后续 repo、agent、docs、history 能按职责扩展。
- 当前只预留 Agent/AI/MCP 扩展结构，不实现真实逻辑：避免跨阶段，也避免把占位能力误描述成真实 AI 能力。
- 使用 `.env.example` 而不是提交 `.env`：保留配置说明，同时避免泄露真实密钥。

## 5. 面试可讲点

- 为什么前端不能直接调用 OpenAI API：浏览器端无法安全保存 API Key，也不适合处理本地仓库读取和文件落盘。
- 为什么工作台要展示“文件树 + Agent 步骤 + 工具日志 + Markdown 预览”：这是产品区别于普通聊天机器人的核心结构，强调可解释的分析流程。
- 为什么 `main.py` 要保持很薄：入口文件只做 app 组装，业务能力按 API、schema、service、agent 分层沉淀。
- 为什么第一阶段不实现 GitHub clone 和 AI 调用：先验证工程骨架、启动链路和页面结构，避免在基础设施未稳定时引入复杂业务。
- 为什么预留 MCP/RAG 但不引入依赖：这些是后续扩展方向，第一阶段引入会增加复杂度，也不符合 MVP 边界。

## 6. 相关 ADR

- `docs/adr/001-采用前后端分离结构.md`
- `docs/adr/002-前端采用Vue3-TypeScript-NaiveUI.md`
- `docs/adr/003-FastAPI后端采用分层骨架.md`
- `docs/adr/004-第一阶段只预留Agent-AI-MCP扩展结构.md`
