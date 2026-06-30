# CodebaseCoach 分阶段开发提示词

使用方式：

每次只复制一个阶段的提示词发给 AI 编码助手。

不要一次性把所有阶段都发给 AI 执行，否则它容易跨阶段乱做。

每个阶段开始前，都要求 AI 先阅读：

* `AI开发提示词.md`
* `产品设计.md`
* 当前阶段相关的页面说明、接口说明或已有代码

UI 框架固定使用：

* Vue 3
* TypeScript
* Vite
* Naive UI

后端固定使用：

* Python 3.11+
* FastAPI
* Pydantic
* GitPython
* OpenAI Python SDK

---

## 阶段复盘、STAR 记录与面试材料沉淀要求

每完成一个开发阶段后，必须同步沉淀该阶段的开发复盘，用于后续整理项目面试材料。

每个阶段都需要在 `docs/stage-notes/` 下创建或更新对应复盘文档。

文件命名建议：

```text
stage-01-项目骨架复盘.md
stage-02-仓库读取复盘.md
stage-03-工作台UI复盘.md
stage-04-核心文件筛选复盘.md
stage-05-AI接入复盘.md
stage-06-Agent可视化复盘.md
stage-07-历史记录复盘.md
stage-08-项目包装复盘.md
stage-09-MCP扩展复盘.md
```

每份阶段复盘文档必须包含：

```md
# 阶段 X：阶段名称复盘

## 1. 本阶段目标

说明本阶段原本要完成什么。

## 2. 实际完成内容

列出本阶段实际实现的功能、接口、页面、服务或文档。

## 3. 遇到的问题与解决方案

每个问题必须使用 STAR + 技术细节结构记录。

### 问题 1：问题标题

#### S - Situation 背景

描述这个问题是在什么项目背景下出现的。

#### T - Task 任务

说明当时需要解决什么目标或约束。

#### A - Action 行动

说明实际采取了哪些技术方案、代码调整、架构调整或调试方式。

#### R - Result 结果

说明问题最终是否解决，解决后带来了什么效果。

#### 技术细节

补充涉及的模块、文件、接口、数据结构、边界条件或关键实现逻辑。

#### 面试表达

用 3～5 句话总结这个问题在面试中可以如何讲述。

## 4. 技术取舍

说明本阶段涉及到的技术选择、替代方案、优缺点和最终选择理由。

## 5. 面试可讲点

总结本阶段可以用于面试回答的问题，例如：

- 这个功能为什么要这样设计？
- 这项技术在项目中承担什么角色？
- 遇到了什么困难？
- 如何解决？
- 有没有类似技术？
- 为什么最后这么选？
```

复盘要求：

1. 不允许编造不存在的问题。
2. 如果本阶段没有明显 bug，需要记录“实现取舍”或“设计难点”。
3. 每个阶段至少沉淀 2 个面试可讲点。
4. 遇到重要架构决策时，需要同步在 `docs/adr/` 下新增 ADR 文档。
5. 第八阶段需要读取所有 `docs/stage-notes/`，统一整理成 `docs/interview/` 面试材料。
6. mock 能力和真实 AI 能力必须区分清楚，不能把 mock 描述成真实 AI 能力。
7. 文档内容必须和当前代码实现一致，不要夸大未实现功能。

重要 ADR 记录建议：

```text
docs/adr/001-为什么使用FastAPI.md
docs/adr/002-为什么使用GitPython而不是GitHubAPI.md
docs/adr/003-为什么使用可控工作流Agent.md
docs/adr/004-为什么第一版不使用数据库.md
docs/adr/005-为什么保留mock模式.md
docs/adr/006-如何处理token限制.md
docs/adr/007-如何减少AI幻觉.md
```

ADR 文档模板：

```md
# ADR-编号：决策标题

## 背景

说明为什么出现这个技术决策。

## 备选方案

列出可选方案，例如 A / B / C。

## 决策

说明最终选择了什么方案。

## 原因

说明选择该方案的理由。

## 代价

说明该方案带来的限制、风险或后续维护成本。

## 结果

说明该决策在当前项目中的实际效果。
```



## 第一阶段提示词：项目基础结构和前后端骨架

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，然后只执行第一阶段：项目基础结构和前后端骨架。

本阶段目标：

* 创建 CodebaseCoach 项目目录结构
* 建立 Vue 3 + TypeScript + Vite 前端项目
* 接入 Naive UI
* 建立 Python + FastAPI 后端项目
* 建立前后端基础启动命令
* 创建首页、分析工作台、文档页、历史记录页、设置页的页面骨架
* 创建 FastAPI `/health` 接口
* 创建 `.env.example`
* 创建 `generated_docs/`、`temp_repos/`、`data/` 目录
* 创建基础 README

推荐目录：

```text
codebase-coach/
├── apps/
│   ├── web/
│   └── server/
├── docs/
│   ├── 产品设计.md
│   ├── AI阶段提示词.md
│   └── AI开发提示词.md
├── generated_docs/
├── temp_repos/
├── data/
├── README.md
└── .gitignore
```

约束：

* 不要实现真实 AI 调用
* 不要实现 GitHub clone
* 不要实现复杂 UI
* 不要引入 LangChain、MCP、RAG
* 不要把 API Key 写死到代码里
* 不要使用 shadcn-vue、Element Plus 或其他 UI 框架
* 前端必须使用 Naive UI
* 后端必须使用 FastAPI

本阶段额外复盘要求：

完成后请重点记录以下问题：

1. 为什么项目采用前后端分离结构？
2. Vue 3 + TypeScript + Naive UI 在本项目中分别承担什么角色？
3. FastAPI 后端骨架为什么要单独拆分目录，而不是都写在 `main.py`？
4. 当前阶段有没有为了后续 Agent、AI 调用、MCP 扩展预留结构？

请将这些问题写入：

```text
docs/stage-notes/stage-01-项目骨架复盘.md
```

每个问题都必须按照 STAR + 技术细节结构记录。

验收：

* 前端可以启动并看到基础页面
* 后端可以启动并访问 `/health`
* 前端路由可以切换：首页、分析工作台、文档页、历史记录页、设置页
* Naive UI 已正确接入
* `.env.example` 存在
* 目录结构符合规划

完成后请运行：

* 前端：`pnpm install`、`pnpm dev`、`pnpm build`
* 后端：`pip install -r requirements.txt`、`uvicorn app.main:app --reload --port 8000`
* 如果配置了测试：`pytest`
* 如果配置了格式检查：`ruff check .`

最后汇报：

* 修改了哪些文件
* 当前已完成什么
* 哪些检查通过
* 是否有未解决问题
* 下一阶段建议
* 同步创建或更新对应的 `docs/stage-notes/` 阶段复盘文档
* 复盘文档中必须使用 STAR + 技术细节结构记录本阶段遇到的问题、实现取舍和面试可讲点

---

## 第二阶段提示词：GitHub URL 解析和本地仓库读取

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，然后只执行第二阶段：GitHub URL 解析和本地仓库读取。

本阶段目标：

* 实现 GitHub URL 解析
* 实现 `/api/repo/parse` 接口
* 实现 GitPython clone 仓库到 `temp_repos/`
* 实现基础目录树生成
* 实现过滤无关目录和文件
* 实现读取 README、package.json、requirements.txt、pyproject.toml 等基础文件
* 定义相关 Pydantic schema
* 给前端提供一个仓库预分析接口

建议接口：

```text
POST /api/repo/parse
POST /api/repo/scan
```

输入示例：

```json
{
  "repo_url": "https://github.com/modelcontextprotocol/typescript-sdk"
}
```

输出至少包含：

```json
{
  "owner": "modelcontextprotocol",
  "repo": "typescript-sdk",
  "repo_url": "https://github.com/modelcontextprotocol/typescript-sdk",
  "file_tree": [],
  "basic_files": []
}
```

约束：

* 不要真实调用 AI
* 不要生成最终文档
* 不要一次性读取所有文件内容
* 必须过滤 `.git`、`node_modules`、`dist`、`build`、`.venv`、`__pycache__`
* 必须限制单文件读取大小
* clone 失败时返回结构化错误
* 后端逻辑不要写在 `main.py` 里

本阶段额外复盘要求：

完成后请重点记录以下问题：

1. 为什么选择 GitPython 读取仓库，而不是第一版直接使用 GitHub API？
2. clone 公开仓库时可能遇到哪些失败场景？如何做结构化错误处理？
3. 为什么要过滤 `.git`、`node_modules`、`dist`、`build`、`.venv` 等目录？
4. 为什么不能一次性读取所有文件内容？
5. 单文件大小限制和目录树深度限制分别解决什么问题？

请将这些问题写入：

```text
docs/stage-notes/stage-02-仓库读取复盘.md
```

每个问题都必须按照 STAR + 技术细节结构记录。

如果本阶段形成重要技术决策，请新增：

```text
docs/adr/002-为什么使用GitPython而不是GitHubAPI.md
```

验收：

* 输入合法 GitHub URL 可以解析 owner/repo
* 可以 clone 公开 GitHub 仓库
* 可以返回目录树
* 可以返回基础文件摘要
* 无效 URL 返回 400
* clone 失败不会导致服务崩溃

完成后请运行：

* 后端：`python -m compileall app`
* 后端：`uvicorn app.main:app --reload --port 8000`
* 如已配置：`pytest`、`ruff check .`

最后汇报修改文件、验证结果和下一阶段建议，并同步创建或更新对应的 `docs/stage-notes/` 阶段复盘文档。

---

## 第三阶段提示词：前端分析工作台 UI 和 mock 数据

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，然后只执行第三阶段：前端分析工作台 UI 和 mock 数据。

本阶段目标：

* 使用 Naive UI 实现分析工作台布局
* 实现 GitHub 仓库输入区域
* 实现仓库文件树展示
* 实现核心文件列表展示
* 实现 Agent 执行步骤展示
* 实现工具调用日志展示
* 实现 Markdown 文档预览区域
* 先使用 mock 数据完成 UI，不依赖真实后端完整流程

分析工作台布局：

```text
顶部：仓库信息 + 操作按钮
左侧：文件树 + 核心文件
中间：Agent Steps + Tool Logs
右侧：Markdown Preview
```

推荐 Naive UI 组件：

* `n-layout`
* `n-card`
* `n-input`
* `n-button`
* `n-tree`
* `n-steps`
* `n-timeline`
* `n-tag`
* `n-tabs`
* `n-scrollbar`
* `n-alert`
* `n-spin`

约束：

* 不要实现真实 AI 调用
* 不要在前端写死最终业务逻辑
* 不要使用其他 UI 框架
* 不要做成单一聊天框
* 视觉上要体现“AI 工作台”而不是后台管理系统
* 常驻内容区域尽量少用重阴影

本阶段额外复盘要求：

完成后请重点记录以下问题：

1. 为什么分析工作台不能做成普通聊天框？
2. 文件树、Agent Steps、Tool Logs、Markdown Preview 分别解决什么用户问题？
3. Naive UI 的哪些组件用于支撑“AI 工作台”结构？
4. mock 数据在 UI 开发阶段的作用是什么？
5. 如何避免前端 mock 数据和后端真实接口结构脱节？

请将这些问题写入：

```text
docs/stage-notes/stage-03-工作台UI复盘.md
```

每个问题都必须按照 STAR + 技术细节结构记录。

验收：

* 页面能展示 mock 文件树
* 页面能展示 mock Agent 步骤
* 页面能展示 mock 工具调用日志
* 页面能展示 mock Markdown 文档
* 页面布局清晰，适合演示
* 窗口宽度变化时布局不严重错乱

完成后请运行：

* 前端：`pnpm build`
* 如已配置：`pnpm lint`

最后汇报修改文件、验证结果和下一阶段建议，并同步创建或更新对应的 `docs/stage-notes/` 阶段复盘文档。

---

## 第四阶段提示词：核心文件筛选和 mock 文档生成

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，然后只执行第四阶段：核心文件筛选和 mock 文档生成。

本阶段目标：

* 后端实现核心文件筛选规则
* 根据目录树筛选 5 到 12 个核心文件
* 读取核心文件内容摘要
* 实现 mock 文档生成，不调用真实 AI
* 将生成结果保存为 Markdown 文件
* 前端调用后端接口并展示真实目录树、核心文件和 mock 文档

建议接口：

```text
POST /api/agent/analyze/mock
```

核心文件筛选规则：

* 优先 README、package.json、pyproject.toml、requirements.txt
* 优先入口文件 main、index、app、server
* 优先 src、app、core、agent、tools、services、api、routes 目录
* 跳过 test、dist、build、node_modules、.git
* 单文件超过限制时只读取前 N 字符
* 最多读取 12 个核心文件

约束：

* 本阶段继续使用 mock AI
* 不要接入 OpenAI
* 不要引入 LangChain
* 不要做 RAG
* 不要读取二进制文件
* 生成文档必须保存到 `generated_docs/`

本阶段额外复盘要求：

完成后请重点记录以下问题：

1. 为什么不能把整个仓库直接交给 AI？
2. 如何判断哪些文件是核心文件？
3. 如何处理仓库文件过多、目录过深、单文件过大的问题？
4. 为什么要记录核心文件的选择原因？
5. 规则筛选和直接让大模型判断相比，各自有什么优缺点？
6. mock 文档生成在第一版开发中的价值是什么？

请将这些问题写入：

```text
docs/stage-notes/stage-04-核心文件筛选复盘.md
```

每个问题都必须按照 STAR + 技术细节结构记录。

如果本阶段形成重要技术决策，请新增：

```text
docs/adr/006-如何处理token限制.md
docs/adr/005-为什么保留mock模式.md
```

验收：

* 输入 GitHub URL 后可以完成完整 mock 分析流程
* 前端能展示真实文件树
* 前端能展示后端筛选出的核心文件
* 前端能展示 mock Markdown 文档
* `generated_docs/` 中能看到生成的 `.md` 文件
* 无 API Key 时流程可完整演示

完成后请运行：

* 前端：`pnpm build`
* 后端：`python -m compileall app`
* 如已配置：`pytest`、`ruff check .`

最后汇报修改文件、验证结果和下一阶段建议，并同步创建或更新对应的 `docs/stage-notes/` 阶段复盘文档。

---

## 第五阶段提示词：OpenAI Python SDK 接入和真实文档生成

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，然后只执行第五阶段：OpenAI Python SDK 接入和真实文档生成。

本阶段目标：

* 接入 OpenAI Python SDK
* 通过 `.env` 读取 `OPENAI_API_KEY` 和 `OPENAI_MODEL`
* 封装 `llm_service.py`
* 将 Prompt 统一放入 `agent/prompts.py`
* 实现真实 AI 生成项目概览、技术栈分析、核心模块、面试问答、简历描述、PR 方向
* 没有 API Key 时自动回退到 mock 模式
* AI 调用失败时返回结构化错误

建议生成文档：

* `01-项目概览.md`
* `02-技术栈分析.md`
* `03-核心模块解析.md`
* `04-核心流程说明.md`
* `05-面试问题与回答.md`
* `06-简历描述.md`
* `07-可贡献PR方向.md`

Prompt 要求：

* 必须引用具体文件路径
* 不允许编造未提供的文件
* 信息不足时写“不确定”
* 必须面向前端开发者解释
* 必须面向实习面试准备组织内容
* 必须区分事实、推测和建议

约束：

* 前端不能直接调用 OpenAI API
* API Key 不能写死到代码里
* `.env` 不能提交到 GitHub
* 所有 OpenAI 调用必须经过 `llm_service.py`
* Prompt 不能散落在路由函数里
* 不要引入复杂 Agent 框架

本阶段额外复盘要求：

完成后请重点记录以下问题：

1. 为什么 OpenAI 调用要统一封装到 `llm_service.py`？
2. 为什么 Prompt 要统一放到 `agent/prompts.py`？
3. 没有 API Key 时为什么要自动回退到 mock 模式？
4. AI 调用失败时如何保证前端不崩溃？
5. 如何减少模型编造文件、胡说和输出格式不稳定的问题？
6. 为什么要求 AI 输出引用具体文件路径，并区分事实、推测和建议？

请将这些问题写入：

```text
docs/stage-notes/stage-05-AI接入复盘.md
```

每个问题都必须按照 STAR + 技术细节结构记录。

如果本阶段形成重要技术决策，请新增：

```text
docs/adr/007-如何减少AI幻觉.md
```

验收：

* 配置 API Key 后可以生成真实 Markdown 文档
* 不配置 API Key 时 mock 模式仍可运行
* AI 生成内容中包含具体文件路径
* 文档能保存到 `generated_docs/`
* 前端能展示真实生成结果
* AI 调用失败时 UI 不崩溃

完成后请运行：

* 前端：`pnpm build`
* 后端：`python -m compileall app`
* 如已配置：`pytest`、`ruff check .`

最后汇报修改文件、验证结果和下一阶段建议，并同步创建或更新对应的 `docs/stage-notes/` 阶段复盘文档。

---

## 第六阶段提示词：Agent 执行过程可视化和状态联动

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，然后只执行第六阶段：Agent 执行过程可视化和状态联动。

本阶段目标：

* 完善 Agent Step 数据结构
* 完善 Tool Call Log 数据结构
* 后端在每个分析阶段记录步骤状态
* 前端展示步骤状态变化
* 前端展示工具调用日志
* 前端展示分析中、成功、失败、跳过等状态
* 支持用户重新分析当前仓库
* 支持清理当前分析结果

可选增强：

* 使用轮询获取状态
* 或使用 SSE 流式推送状态

第一版如 SSE 实现成本较高，可以先使用一次性返回完整步骤列表。

约束：

* 不要为了可视化破坏后端工作流结构
* 不要把工具调用日志写成纯字符串
* 不要让前端猜测后端状态
* 失败步骤必须有错误说明
* mock 模式也要生成步骤和工具日志

本阶段额外复盘要求：

完成后请重点记录以下问题：

1. 为什么要展示 Agent 执行步骤？
2. AgentStep 和 ToolCallLog 分别解决什么问题？
3. 如何让用户知道系统读了哪些文件、为什么读这些文件？
4. 一次性返回步骤列表和 SSE 流式推送有什么区别？
5. 为什么第一版可以先不用 SSE？
6. Agent 可视化如何提升项目的可解释性和面试讲述价值？

请将这些问题写入：

```text
docs/stage-notes/stage-06-Agent可视化复盘.md
```

每个问题都必须按照 STAR + 技术细节结构记录。

验收：

* 分析完成后能看到完整 Agent 执行步骤
* 每个步骤有状态、说明、耗时
* 能看到读取了哪些文件
* 能看到哪些文件被用于 AI 上下文
* 分析失败时前端显示失败步骤和错误原因

完成后请运行：

* 前端：`pnpm build`
* 后端：`python -m compileall app`

最后汇报修改文件、验证结果和下一阶段建议，并同步创建或更新对应的 `docs/stage-notes/` 阶段复盘文档。

---

## 第七阶段提示词：历史记录、文档管理和导出

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，然后只执行第七阶段：历史记录、文档管理和导出。

本阶段目标：

* 实现 `data/history.json`
* 保存每次分析记录
* 历史记录页展示分析过的仓库
* 支持打开历史分析结果
* 支持删除历史记录
* 支持重新分析
* 支持复制单篇 Markdown
* 支持下载生成文档
* 支持下载全部 Markdown 压缩包，可选

历史记录字段至少包括：

* id
* repo_url
* owner
* repo
* status
* created_at
* completed_at
* docs_dir
* core_files_count
* error_message

约束：

* 第一版历史记录使用 JSON，不要引入数据库
* 删除历史记录时不要误删用户手动保存的文件
* 重新分析应创建新的分析记录
* 生成文档必须仍然是 Markdown 文件

本阶段额外复盘要求：

完成后请重点记录以下问题：

1. 为什么第一版历史记录使用 JSON，而不是直接上数据库？
2. Markdown 文件作为生成文档主存储有什么优点？
3. 删除历史记录时为什么不能误删用户手动保存的文件？
4. 重新分析为什么应该创建新的分析记录？
5. 如果后续要多人使用，JSON 存储需要如何升级？

请将这些问题写入：

```text
docs/stage-notes/stage-07-历史记录复盘.md
```

每个问题都必须按照 STAR + 技术细节结构记录。

如果本阶段形成重要技术决策，请新增：

```text
docs/adr/004-为什么第一版不使用数据库.md
```

验收：

* 每次分析后历史记录会增加
* 历史记录页能打开旧文档
* 可以删除历史记录
* 可以复制 Markdown 内容
* 可以下载 Markdown 文件

完成后请运行：

* 前端：`pnpm build`
* 后端：`python -m compileall app`

最后汇报修改文件、验证结果和下一阶段建议，并同步创建或更新对应的 `docs/stage-notes/` 阶段复盘文档。

---

## 第八阶段提示词：项目包装、README 和面试材料

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，然后只执行第八阶段：项目包装、README 和面试材料。

本阶段目标：

* 完善项目 README
* 补充项目架构说明
* 补充核心流程图说明
* 补充 API 文档
* 补充 Prompt 设计说明
* 补充面试亮点说明
* 补充常见面试问题和回答
* 补充运行截图占位说明
* 补充部署和启动方式

README 至少包含：

* 项目背景
* 核心功能
* 技术栈
* 架构设计
* Agent 工作流
* 本地运行方式
* 环境变量说明
* 项目亮点
* 后续规划

面试材料至少包含：

* 为什么做这个项目
* 和直接问 ChatGPT 有什么区别
* 如何筛选核心文件
* 如何解决 token 限制
* 如何减少幻觉
* 如何设计 Prompt
* 如何处理 AI 调用失败
* 前端如何展示 Agent 过程
* 后续如何扩展 MCP / RAG

约束：

* 不要夸大项目能力
* 不要声称实现了未完成的功能
* 不要把 mock 功能描述成真实 AI 能力
* 文档必须和当前代码一致

本阶段额外复盘要求：

请读取 `docs/stage-notes/` 下所有阶段复盘文档，将每个阶段的“遇到的问题、解决方案、技术取舍、面试可讲点”整理到 `docs/interview/` 目录。

至少生成：

```text
docs/interview/项目介绍.md
docs/interview/技术选型说明.md
docs/interview/开发困难复盘.md
docs/interview/技术对比与取舍.md
docs/interview/高频面试问答.md
```

整理要求：

1. 不要编造未在阶段复盘中出现的问题。
2. 不要夸大项目能力。
3. mock 能力和真实 AI 能力必须区分清楚。
4. 每个面试问题都要结合 CodebaseCoach 的真实实现回答。
5. 面试回答需要覆盖以下四类问题：
   - 这个项目到底是什么？
   - 这个技术在项目中承担什么角色？为什么用它？
   - 开发中遇到了哪些困难？如何解决？
   - 类似技术有哪些？如何权衡后做出选择？

请将本阶段自身复盘写入：

```text
docs/stage-notes/stage-08-项目包装复盘.md
```

验收：

* README 可以指导别人启动项目
* 面试材料可以直接用于复习
* 技术亮点表达清晰
* 已完成和未完成能力边界明确

完成后请运行：

* 前端：`pnpm build`
* 后端：`python -m compileall app`

最后汇报修改文件、验证结果和后续建议，并同步创建或更新对应的 `docs/stage-notes/` 阶段复盘文档。

---

## 第九阶段可选提示词：MCP Server 扩展

请先阅读 `AI开发提示词.md` 和 `产品设计.md`，并确认 MVP 已经完成，然后只执行第九阶段：MCP Server 扩展。

本阶段目标：

* 将仓库读取能力封装为 MCP tools
* 实现 `repo.get_tree`
* 实现 `repo.read_file`
* 实现 `repo.search_code`
* 实现 `doc.write_markdown`
* 保留原有 FastAPI 工作流
* 在 README 中说明 MCP 扩展价值

约束：

* 不要为了 MCP 重写整个项目
* 不要破坏现有 MVP
* MCP 是加分项，不是主线功能
* 工具输入输出必须结构化

本阶段额外复盘要求：

完成后请重点记录以下问题：

1. 为什么 MCP 是第一版后的扩展，而不是 MVP 主线？
2. MCP tools 和原有 FastAPI service 层是什么关系？
3. 为什么不要为了 MCP 重写整个项目？
4. MCP 工具暴露时为什么要避免 shell、git push、任意文件写入等高风险能力？
5. MCP 扩展相比普通后端接口有什么工程化价值？

请将这些问题写入：

```text
docs/stage-notes/stage-09-MCP扩展复盘.md
```

每个问题都必须按照 STAR + 技术细节结构记录。

验收：

* MCP server 能启动
* 至少 3 个工具可调用
* 原有前端和 FastAPI 流程不受影响
* README 说明 MCP 的作用和使用方式

完成后请运行对应检查，并汇报修改文件、验证结果和后续建议。
