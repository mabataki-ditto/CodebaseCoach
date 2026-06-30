# CodebaseCoach AI 开发提示词

你是一个资深 Vue 3 + Python FastAPI + AI 应用开发助手。请在当前仓库中开发 CodebaseCoach。

这是开发实现提示词，不是产品介绍。你需要直接阅读项目文件、产品设计文档和阶段提示词，然后分阶段实现可运行应用。

---

## 一、当前项目目标

项目名称：CodebaseCoach

中文名：开源项目学习与面试准备 Agent

项目类型：面向前端开发者和 AI 应用开发实习求职者的 GitHub 仓库分析工具。

核心能力：

* 输入 GitHub 仓库地址
* 自动解析仓库 owner / repo
* clone 公开仓库到本地临时目录
* 生成项目目录树
* 读取 README、package.json 等基础文件
* 自动筛选核心文件
* 调用 AI 生成项目学习文档
* 生成面试问题与回答
* 生成简历描述
* 生成可贡献 PR 方向
* 将结果保存为 Markdown 文件
* 前端展示文件树、Agent 步骤、工具调用日志和 Markdown 预览

不要做成普通聊天软件，也不要做成完整 IDE。

它是一个 AI 驱动的开源项目学习与面试准备工作流工具。

---

## 二、固定技术栈

前端：

* Vue 3
* TypeScript
* Vite
* Naive UI
* Pinia
* Vue Router
* markdown-it
* highlight.js

后端：

* Python 3.11+
* FastAPI
* Pydantic
* Uvicorn
* GitPython
* OpenAI Python SDK
* python-dotenv

第一版不使用：

* shadcn-vue
* Element Plus
* Nuxt
* Electron
* LangChain
* MCP
* RAG
* 数据库

LangChain、MCP、RAG 可以作为 MVP 之后的扩展，不要第一阶段引入。

---

## 三、开发总目标

实现一个可本地运行的前后端分离 AI 应用。

前端负责：

* 页面布局
* 用户交互
* 仓库地址输入
* 文件树展示
* Agent 执行步骤展示
* 工具调用日志展示
* Markdown 渲染预览
* 历史记录展示
* 设置页展示

后端负责：

* GitHub URL 解析
* 仓库 clone
* 文件树生成
* 文件过滤和读取
* 核心文件筛选
* Prompt 构建
* OpenAI API 调用
* mock AI 回退
* Markdown 文件生成
* 历史记录保存
* 结构化错误返回

前端不直接请求 OpenAI API。

OpenAI API Key 只允许在后端 `.env` 中配置。

---

## 四、推荐项目目录结构

```text
codebase-coach/
├── apps/
│   ├── web/
│   │   ├── src/
│   │   │   ├── api/
│   │   │   ├── assets/
│   │   │   ├── components/
│   │   │   ├── pages/
│   │   │   ├── router/
│   │   │   ├── stores/
│   │   │   ├── types/
│   │   │   ├── App.vue
│   │   │   └── main.ts
│   │   ├── index.html
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── vite.config.ts
│   │
│   └── server/
│       ├── app/
│       │   ├── main.py
│       │   ├── api/
│       │   │   ├── repo.py
│       │   │   ├── agent.py
│       │   │   ├── docs.py
│       │   │   └── history.py
│       │   ├── agent/
│       │   │   ├── workflow.py
│       │   │   ├── tools.py
│       │   │   └── prompts.py
│       │   ├── services/
│       │   │   ├── repo_parser.py
│   	|	|	├── github_service.py
        |   │   ├── file_tree_service.py
        |   │   ├── file_selector_service.py
        |   │   ├── ai_context_builder.py
        |   │   ├── llm_service.py
        |   │   ├── doc_storage_service.py
        |   │   ├── history_service.py
        |   │   ├── config_service.py
        |   │   ├── analysis_record_service.py
        |   │   ├── agent_step_service.py
        |   │   ├── tool_log_service.py
        |   │   └── llm_call_service.py
│       │   ├── schemas/
│       │   │   ├── repo.py
│       │   │   ├── agent.py
│       │   │   ├── docs.py
│       │   │   └── history.py
│       │   ├── core/
│       │   │   ├── config.py
│       │   │   └── errors.py
│       │   └── utils/
│       │       └── path_utils.py
│       ├── requirements.txt
│       ├── .env.example
│       └── README.md
│
├── docs/
|	|--
│   ├── 产品设计.md
│   ├── AI阶段提示词.md
│   └── AI开发提示词.md
├── generated_docs/
├── temp_repos/
├── data/
├── README.md
└── .gitignore
```

如果当前仓库已有结构，应在不破坏现有代码的前提下调整。

不要把所有逻辑堆到一个文件里。

---

## 五、工程原则

1. 先实现可运行 MVP，再做复杂能力。

2. 前端使用 Vue 3 Composition API。

3. 前端 UI 固定使用 Naive UI。

4. 后端使用 FastAPI 分层组织。

5. API 层只处理请求和响应，不写复杂业务逻辑。

6. services 层处理具体业务能力。

7. agent 层处理工作流、工具调用和 Prompt。

8. schemas 层定义 Pydantic 请求和响应模型。

9. OpenAI 调用必须统一封装在 `llm_service.py`。

10. Prompt 必须统一放在 `agent/prompts.py`。

11. 生成文档必须保存为 Markdown 文件。

12. 无 API Key 时必须保留 mock 模式，保证项目可演示。

13. 所有错误必须结构化返回，不要让前端崩溃。

14. 不要一开始引入 LangChain、MCP、RAG。

15. 不要为了炫技破坏项目清晰度。

---

## 六、前端实现要求

### 1. 页面

必须实现：

* 首页
* 分析工作台
* 文档页
* 历史记录页
* 设置页

### 2. 首页

首页包含：

* 项目名称
* 一句话定位
* GitHub 仓库地址输入框
* 开始分析按钮
* 示例仓库入口
* 最近分析入口
* 项目能力说明

首页不是聊天页。

### 3. 分析工作台

必须包含：

* 仓库信息区域
* 文件树区域
* 核心文件列表
* Agent 执行步骤
* 工具调用日志
* Markdown 文档预览

推荐 Naive UI 组件：

* `n-layout`
* `n-card`
* `n-grid`
* `n-input`
* `n-button`
* `n-tree`
* `n-steps`
* `n-timeline`
* `n-tag`
* `n-tabs`
* `n-scrollbar`
* `n-spin`
* `n-alert`
* `n-message`

### 4. 文档页

用于展示生成的 Markdown 文档。

必须支持：

* 文档列表
* Markdown 预览
* 复制 Markdown
* 下载 Markdown

### 5. 历史记录页

用于展示历史分析。

必须支持：

* 查看历史记录
* 打开历史文档
* 重新分析
* 删除记录

第一版可以使用后端 JSON 文件保存历史记录。

### 6. 设置页

第一版只需要：

* 后端服务地址展示
* 后端健康检查
* 当前模型展示
* 是否启用 mock 模式展示
* 显示设置
* 缓存清理入口
* 关于项目

不要在前端保存或展示完整 API Key。

---

## 七、后端实现要求

### 1. FastAPI 入口

`app/main.py` 只负责：

* 创建 FastAPI app
* 注册 router
* 配置 CORS
* 提供 `/health`

不要把业务逻辑写在 `main.py`。

### 2. API 路由

建议路由：

```text
GET  /health
POST /api/repo/parse
POST /api/repo/scan
POST /api/agent/analyze
POST /api/agent/analyze/mock
GET  /api/docs/{analysis_id}
GET  /api/history
DELETE /api/history/{id}
```

### 3. GitHub URL 解析

必须支持：

* `https://github.com/owner/repo`
* `https://github.com/owner/repo.git`

无效 URL 返回 400。

### 4. 仓库 clone

使用 GitPython。

clone 到：

```text
temp_repos/{owner}_{repo}_{timestamp}/
```

clone 失败必须返回结构化错误。

### 5. 文件树生成

必须过滤：

* `.git`
* `node_modules`
* `dist`
* `build`
* `coverage`
* `.venv`
* `venv`
* `__pycache__`
* `.next`
* `.nuxt`
* `.cache`
* `.idea`
* `.vscode`

不要读取二进制文件。

### 6. 核心文件筛选

优先文件：

* `README.md`
* `package.json`
* `pyproject.toml`
* `requirements.txt`
* `tsconfig.json`
* `vite.config.ts`
* `src/main.ts`
* `src/index.ts`
* `src/App.vue`
* `main.py`
* `app.py`
* `server.py`

优先目录关键字：

* `src`
* `app`
* `core`
* `agent`
* `agents`
* `tools`
* `services`
* `api`
* `routes`
* `components`

最多读取 12 个核心文件。

单文件内容必须限制长度。

### 7. AI 调用

使用 OpenAI Python SDK。

`.env` 示例：

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4.1-mini
TEMP_REPO_DIR=./temp_repos
GENERATED_DOCS_DIR=./generated_docs
MOCK_MODE=true
```

调用规则：

* API Key 从环境变量读取
* 所有调用集中到 `llm_service.py`
* Prompt 统一放到 `agent/prompts.py`
* 调用失败返回结构化错误
* 没有 API Key 时使用 mock 输出

---

## 八、Agent 工作流要求

第一版采用可控工作流 Agent。

不要一开始使用复杂自主 Agent。

核心函数建议：

```text
run_codebase_analysis_workflow(repo_url: str) -> AnalyzeRepoResponse
```

工作流步骤：

```text
1. parse_repo_url
2. clone_repository
3. build_file_tree
4. read_basic_files
5. select_core_files
6. read_core_files
7. build_analysis_context
8. generate_project_overview
9. generate_tech_stack_doc
10. generate_core_modules_doc
11. generate_interview_qa
12. generate_resume_description
13. generate_pr_suggestions
14. save_markdown_docs
15. save_history_record
```

每一步都应生成 Agent Step 记录。

每个工具调用都应生成 Tool Call Log。

---

## 九、Prompt 设计要求

Prompt 必须满足：

* 要求模型引用具体文件路径
* 要求模型不要编造未提供的文件
* 信息不足时写“不确定”
* 输出 Markdown
* 面向前端开发者解释
* 面向 AI 应用开发实习面试准备组织内容
* 区分项目事实、合理推测和优化建议

推荐 Prompt 类型：

* `PROJECT_OVERVIEW_PROMPT`
* `TECH_STACK_PROMPT`
* `CORE_MODULES_PROMPT`
* `CORE_FLOW_PROMPT`
* `INTERVIEW_QA_PROMPT`
* `RESUME_DESCRIPTION_PROMPT`
* `PR_SUGGESTION_PROMPT`

不要把 Prompt 写在路由函数里。

---

## 十、数据存储规则

### 1. generated_docs

AI 生成的文档必须保存为 Markdown 文件。

目录：

```text
generated_docs/{owner}_{repo}_{timestamp}/
```

### 2. history.json

历史记录保存到：

```text
data/history.json
```

### 3. config.json

用户配置保存到：

```text
data/config.json
```

### 4. temp_repos

clone 的仓库存放到：

```text
temp_repos/
```

不要提交 `temp_repos/`、`generated_docs/` 中的用户生成内容，除非只是保留 `.gitkeep`。

---

## 十一、错误处理要求

所有错误必须结构化。

建议错误格式：

```json
{
  "error": {
    "code": "REPO_CLONE_FAILED",
    "message": "仓库克隆失败",
    "detail": "具体错误信息"
  }
}
```

错误类型至少包括：

* `INVALID_GITHUB_URL`
* `REPO_CLONE_FAILED`
* `REPO_TOO_LARGE`
* `FILE_READ_FAILED`
* `OPENAI_API_KEY_MISSING`
* `LLM_CALL_FAILED`
* `DOC_SAVE_FAILED`
* `UNKNOWN_ERROR`

前端必须展示错误，不要崩溃。

---

## 十二、开发过程要求

每次开发前：

1. 先阅读 `docs/产品设计.md`。
2. 先阅读 `docs/AI开发提示词.md`。
3. 如果是阶段开发，阅读当前阶段提示词。
4. 检查当前项目结构和已有代码。
5. 明确本次只做当前阶段，不跨阶段实现复杂功能。

每次开发中：

1. 不要一次性大改所有模块。
2. 优先保证可运行。
3. API schema 先稳定。
4. UI 先可用，再优化视觉。
5. mock 模式必须保留。
6. 不要引入无关依赖。
7. 不要把安全信息写进代码。

每次开发后：

1. 前端运行 `pnpm build`。
2. 后端运行 `python -m compileall app`。
3. 如果配置了测试，运行 `pytest`。
4. 如果配置了 lint，运行 `ruff check .`。
5. 如果检查失败，优先修复。
6. 如果某项无法运行，必须说明原因。

---

## 十三、禁止事项

* 不要使用 shadcn-vue。
* 不要使用 Element Plus。
* 不要使用 Nuxt 重写项目。
* 不要把项目做成普通聊天软件。
* 不要把项目做成完整 IDE。
* 不要前端直接调用 OpenAI API。
* 不要把 API Key 提交到 GitHub。
* 不要把所有后端逻辑写进 `main.py`。
* 不要把所有前端逻辑写进一个 Vue 文件。
* 不要一次性读取整个仓库给模型。
* 不要读取二进制文件。
* 不要忽略文件大小限制。
* 不要让 AI 编造未提供的文件。
* 不要把 mock 功能包装成真实 AI 能力。
* 不要第一阶段就引入 LangChain、MCP、RAG。
* 不要生成无法编辑、无法保存的 AI 内容。
* 不要在 API 路由函数中直接读写 `history.json`、`config.json` 或生成文档元信息。
* 不要在 `AgentWorkflow` 中直接操作 JSON 文件或未来数据库。
* 所有历史记录、配置、文档元信息、Agent 步骤、工具日志和模型调用记录必须通过 service 封装。

---

## 十四、最先执行的任务

请从第一阶段开始：

1. 创建项目目录结构。
2. 搭建 Vue 3 + TypeScript + Vite 前端。
3. 接入 Naive UI。
4. 搭建 FastAPI 后端。
5. 创建 `/health` 接口。
6. 创建首页、分析工作台、文档页、历史记录页、设置页骨架。
7. 创建 `generated_docs/`、`temp_repos/`、`data/` 目录。
8. 创建 `.env.example`。
9. 保证前端和后端都能本地启动。

完成第一阶段后，再继续第二阶段。

不要跳到后面的真实 AI、历史记录、MCP 或 RAG。
