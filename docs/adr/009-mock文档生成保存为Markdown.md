# ADR-009：mock 文档生成保存为 Markdown

## 背景

第四阶段要求实现 mock 文档生成，但明确禁止真实 AI 调用、OpenAI 接入、LangChain、MCP 和 RAG。同时，产品设计要求生成文档不能只存在于内存中，必须保存为 Markdown 文件，后续文档页和历史记录页都需要基于这些文件继续扩展。

## 备选方案

### 方案 A：mock 生成后保存 Markdown 文件

基于基础文件摘要和核心文件摘要拼接 mock Markdown，并保存到 `generated_docs/{owner}_{repo}_{timestamp}/`。

优点是无 API Key 也能端到端演示，且符合文档存储规则。缺点是内容只是模板化 mock，不具备真实 AI 分析能力。

### 方案 B：只在接口响应中返回 mock 文档

后端生成 mock 内容后只返回给前端，不写入文件。

优点是实现更少。缺点是违反“生成文档必须保存为 Markdown 文件”的产品要求，也无法支撑后续文档页、历史记录和导出。

### 方案 C：提前接入真实 AI 生成文档

直接调用 OpenAI 生成正式文档。

优点是内容质量更接近最终产品。缺点是跨阶段实现，违反当前阶段约束，也会让无 API Key 演示失败。

## 决策

第四阶段采用方案 A：

- 在 `apps/server/app/agent/workflow.py` 中生成 7 份 mock Markdown。
- 在 `apps/server/app/services/doc_storage_service.py` 中统一保存文件。
- 保存目录为 `generated_docs/{owner}_{repo}_{timestamp}/`。
- 接口响应同时返回文档元信息、相对路径和内容，供前端立即预览。
- 文档内容明确标注“mock 生成器”和“未调用真实 AI”。

## 原因

这个方案能同时满足“流程可演示”和“能力边界诚实”两个要求。前端可以立即展示 Markdown，用户也能在 `generated_docs/` 中看到真实落盘文件。

把文件保存封装在 service 中，也避免把磁盘写入逻辑放进 API 路由或 Agent 工作流细节中。

## 代价

- `generated_docs/` 会产生本地生成内容，需要通过 `.gitignore` 保持不提交用户生成文件。
- mock 文档内容质量有限，只能表达规则化事实、推测和后续建议。
- 后续接入真实 AI 时，需要替换生成逻辑，但可以复用保存服务和前端展示结构。

## 结果

当前真实仓库验收生成了 7 份 Markdown 文件：

- `01-项目概览.md`
- `02-技术栈分析.md`
- `03-核心模块解析.md`
- `04-核心流程说明.md`
- `05-面试问题与回答.md`
- `06-简历描述.md`
- `07-可贡献PR方向.md`

前端工作台可以展示接口返回的文档内容，并明确标记为 mock。
