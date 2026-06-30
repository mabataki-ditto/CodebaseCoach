# ADR-004：第一阶段只预留 Agent、AI 和 MCP 扩展结构

## 背景

CodebaseCoach 后续会有可控工作流 Agent、AI 文档生成、工具调用日志，并可能在 MVP 之后扩展 MCP 或 RAG。但第一阶段的目标是项目基础结构和前后端骨架，明确禁止实现真实 AI 调用、GitHub clone、LangChain、MCP 和 RAG。

需要在不跨阶段的前提下，为后续能力留下清晰位置。

## 备选方案

### 方案 A：只预留目录和模块，不实现业务

创建 `app/agent`、`app/services/llm_service.py`、`generated_docs/`、`temp_repos/`、`data/` 等结构，但不写真实分析逻辑。

优点是符合第一阶段边界，后续 Agent、Prompt、工具调用、LLM 封装和文档保存都有明确落点，也不会引入当前阶段禁止依赖。缺点是会存在空模块，需要通过复盘和 README 说明它们只是结构预留。

### 方案 B：第一阶段直接实现 Agent 或 mock AI

优点是可以更早演示完整流程。缺点是超出当前阶段目标，容易把 mock 能力误描述成真实 AI 能力，也会过早绑定工作流细节。

### 方案 C：完全不预留扩展结构

优点是第一阶段文件最少。缺点是第二阶段以后需要重新调整目录，Prompt、工具调用、LLM 封装容易临时堆进路由或入口文件。

## 决策

第一阶段只预留轻量扩展结构，不实现真实 Agent、AI、MCP 或 RAG：

- `apps/server/app/agent/workflow.py`
- `apps/server/app/agent/tools.py`
- `apps/server/app/agent/prompts.py`
- `apps/server/app/services/llm_service.py`
- `generated_docs/`
- `temp_repos/`
- `data/`

## 原因

后续阶段确实需要 Agent 工作流、Prompt 管理、模型调用封装和文档保存目录，但第一阶段最重要的是证明工程骨架可运行。

只预留结构能降低后续返工成本，同时避免现在引入 LangChain、MCP、RAG 或伪造的 AI 分析逻辑。

## 代价

- 当前存在空模块，短期看起来不完整。
- 后续阶段必须补真实实现，否则这些预留文件没有实际价值。
- 需要持续区分占位、mock 和真实 AI 能力，避免文档夸大当前实现。

## 结果

当前代码只完成骨架。项目没有真实 AI 调用，没有 GitHub clone，没有 LangChain、MCP、RAG 依赖，也没有把 mock 或占位内容描述成真实 AI 能力。
