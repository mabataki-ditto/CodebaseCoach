# ADR-002：前端采用 Vue 3、TypeScript、Vite 和 Naive UI

## 背景

CodebaseCoach 的前端不是普通聊天页，而是一个面向仓库分析的工作台。第一阶段需要实现首页、分析工作台、文档页、历史记录页和设置页，并体现文件树、Agent 步骤、工具日志和 Markdown 预览这些核心结构。

需求明确要求前端必须使用 Naive UI，不能使用 shadcn-vue、Element Plus 或其他 UI 框架。

## 备选方案

### 方案 A：Vue 3 + TypeScript + Vite + Naive UI

优点是完全符合指定技术栈。Vue 3 适合组件化和响应式状态管理，TypeScript 适合约束后续 API 数据结构，Vite 提供轻量开发和构建能力，Naive UI 提供布局、卡片、输入框、树、步骤条、标签、Tabs 和消息反馈等工作台组件。

缺点是后续需要维护类型定义和组件组织方式，避免页面随着功能增长变成大文件。

### 方案 B：Vue 3 + Element Plus

优点是生态成熟，后台系统场景常见。缺点是明确被阶段约束禁止，而且视觉上更偏传统后台，不符合当前轻量 SaaS 工作台方向。

### 方案 C：Nuxt 或其他全栈前端框架

优点是约定式路由和工程能力更完整。缺点是当前项目不需要 SSR，也明确禁止用 Nuxt 重写项目。

## 决策

前端采用 Vue 3 + TypeScript + Vite + Naive UI。

当前实现中：

- `apps/web/src/main.ts` 创建 Vue 应用并接入 Pinia 与 Router。
- `apps/web/src/router/index.ts` 定义五个页面路由。
- `apps/web/src/App.vue` 接入 `n-config-provider` 和 `n-message-provider`。
- `apps/web/src/pages/` 放置五个页面骨架。

## 原因

这个组合能用较少代码搭建可运行的工作台骨架。Naive UI 已经覆盖本阶段需要的基础组件，不需要自建组件库或引入第二套 UI 框架。

TypeScript 在第一阶段的价值主要是保证基础工程类型检查能跑通，并为后续 Agent 步骤、文件树节点、历史记录和文档元数据提供类型基础。

## 代价

- 当前页面仍是骨架和静态占位，后续需要接入真实 API。
- 功能增长后需要抽取复用组件，避免页面文件过大。
- 需要持续控制视觉风格，避免变成默认后台系统界面。

## 结果

当前前端已经能启动、构建并切换五个页面。Naive UI 已在页面中实际使用，`pnpm build` 已通过。第一阶段没有在前端保存或展示完整 API Key，也没有实现真实仓库分析。
