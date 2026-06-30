# 阶段 3：工作台 UI 复盘

## 1. 本阶段目标

本阶段目标是用 Naive UI 和 mock 数据完成分析工作台页面：

- 实现 GitHub 仓库输入区域。
- 展示 mock 文件树。
- 展示 mock 核心文件列表。
- 展示 mock Agent 执行步骤。
- 展示 mock 工具调用日志。
- 展示 mock Markdown 文档预览。
- 布局体现“顶部仓库信息 + 左侧文件树/核心文件 + 中间 Agent/工具日志 + 右侧 Markdown Preview”。
- 页面在窗口宽度变化时不严重错乱。

本阶段不实现真实 AI 调用，不依赖真实后端完整流程，不做成单一聊天框。

## 2. 实际完成内容

- 在 `apps/web/src/main.ts` 正式按需注册当前项目使用到的 Naive UI 组件。
- 新增 `apps/web/src/mocks/workspace.ts`，集中存放第三阶段工作台 mock 数据。
- 重写 `apps/web/src/pages/WorkspacePage.vue`，实现仓库输入、仓库摘要、文件树、核心文件、Agent Steps、Tool Logs、Markdown Preview。
- 更新 `apps/web/src/styles.css`，新增工作台三栏布局、滚动面板、核心文件卡片、Markdown 预览和响应式断点。
- 运行 `pnpm build` 通过。
- 临时启动 Vite dev server，访问 `/workspace` 返回 HTTP 200。

## 3. 遇到的问题与解决方案

### 问题 1：如何让页面体现 AI 工作台，而不是普通后台管理页或聊天框？

#### S - Situation 背景

产品设计明确要求 CodebaseCoach 不是普通聊天软件，也不是完整 IDE。第三阶段需要让工作台第一眼呈现“仓库结构 + Agent 过程 + 文档预览”的产品定位。

#### T - Task 任务

需要在不接入真实后端完整流程的前提下，使用 mock 数据完成清晰可演示的工作台布局。

#### A - Action 行动

采用四区布局：顶部放仓库输入、仓库摘要和操作按钮；左侧放文件树和核心文件；中间放 Agent Steps 与 Tool Logs；右侧放 Markdown Preview。页面使用 Naive UI 的 `n-layout`、`n-card`、`n-input`、`n-button`、`n-tree`、`n-steps`、`n-timeline`、`n-tag`、`n-scrollbar`、`n-alert`、`n-spin`。

#### R - Result 结果

工作台页面能展示完整 mock 分析流程，用户可以看到系统“解析仓库、克隆、生成目录树、读取基础文件、准备筛选核心文件”的过程，而不是面对一个单一输入框。

#### 技术细节

- 页面文件：`apps/web/src/pages/WorkspacePage.vue`。
- mock 数据：`apps/web/src/mocks/workspace.ts`。
- 布局样式：`.workspace-toolbar`、`.workspace-grid`、`.workspace-column`、`.preview-scroll`。
- 窗口宽度低于 `1180px` 时右侧预览下移，低于 `760px` 时切换为单列。

#### 面试表达

我没有把 AI 产品做成聊天框，而是把 AI 分析过程产品化成一个可观察工作台。左侧展示仓库结构，中间展示 Agent 执行过程和工具日志，右侧展示文档预览。这样用户能理解系统读了什么、做了什么、产出了什么。

### 问题 2：为什么第三阶段先使用前端 mock 数据？

#### S - Situation 背景

第二阶段后端已经能解析和扫描仓库，但还没有完整 Agent 流程、核心文件筛选、AI 文档生成和历史记录。第三阶段目标是工作台 UI，不应该被后端未完成能力阻塞。

#### T - Task 任务

需要让页面能演示最终工作台形态，同时不把真实 AI 调用或最终业务逻辑写死在前端。

#### A - Action 行动

将 mock 数据集中放到 `workspace.ts`，页面只消费 mock 文件树、核心文件、Agent 步骤、工具日志和 Markdown 预览数据。仓库输入只做前端格式校验和 mock 切换，不调用真实 AI，也不生成最终文档。

#### R - Result 结果

工作台 UI 可以独立演示，后续接入真实接口时可以把 mock 数据替换为 API 响应，不需要重写页面布局。

#### 技术细节

- `mockFileTree` 对应文件树展示。
- `mockCoreFiles` 对应核心文件列表。
- `mockAgentSteps` 对应 Agent 步骤。
- `mockToolLogs` 对应工具调用日志。
- `mockMarkdownSections` 对应 Markdown 预览。

#### 面试表达

我先用 mock 数据做 UI，是为了让前后端开发解耦。第三阶段只验证页面信息架构和交互形态，不假装已经有真实 AI 能力。后续接入后端时，只需要替换数据来源，工作台结构可以保持稳定。

### 问题 3：Naive UI 为什么要按需注册，而不是全量注册？

#### S - Situation 背景

第一阶段页面使用了 Naive UI 标签，但没有正式全局注册组件。第三阶段补上全局注册后，如果直接 `app.use(naive)`，构建能通过但会出现大 chunk 警告。

#### T - Task 任务

需要确保 Naive UI 在运行时正确接入，同时避免把整个组件库打进主包。

#### A - Action 行动

在 `apps/web/src/main.ts` 中使用 `create({ components: [...] })` 按需注册当前页面实际用到的组件，包括 `NCard`、`NInput`、`NButton`、`NTree`、`NSteps`、`NTimeline`、`NScrollbar`、`NSpin` 等。

#### R - Result 结果

`pnpm build` 通过，JS chunk 从全量注册时的约 `1441KB` 降到约 `443KB`，不再出现大 chunk 警告。

#### 技术细节

- 修改文件：`apps/web/src/main.ts`。
- 使用 API：`create` from `naive-ui`。
- 注册方式：`createApp(App).use(createPinia()).use(router).use(naive).mount('#app')`。

#### 面试表达

Naive UI 全量注册虽然省事，但会把很多没用到的组件打进包里。我改成按需注册当前项目使用的组件，既保证运行时组件可用，也减少首包体积。这个取舍符合 MVP 阶段的性能和工程清晰度要求。

### 问题 4：响应式布局如何避免窗口变化时严重错乱？

#### S - Situation 背景

分析工作台包含文件树、核心文件、步骤、日志和预览五类信息，如果固定三栏宽度，小屏或中等宽度下容易挤压、重叠或横向溢出。

#### T - Task 任务

需要让页面在桌面宽屏、中等宽度和移动宽度下都保持可读，不出现严重错乱。

#### A - Action 行动

使用 CSS Grid 定义三栏布局：左侧 `minmax(260px, 0.85fr)`，中间 `minmax(360px, 1.2fr)`，右侧 `minmax(320px, 1fr)`。在 `1180px` 以下将右侧预览移动到下一行，在 `760px` 以下切换为单列。各内容面板用 `n-scrollbar` 控制高度，避免内容撑爆布局。

#### R - Result 结果

桌面宽屏下呈现三栏工作台，中等宽度下预览区单独占一行，移动宽度下按单列堆叠。构建和 dev server 访问验证均通过。

#### 技术细节

- 关键样式：`.workspace-grid`、`.right-column`、`.repo-summary`。
- 断点：`1180px` 和 `760px`。
- 滚动区域：`.tree-scroll`、`.core-file-scroll`、`.tool-log-scroll`、`.preview-scroll`。

#### 面试表达

工作台信息密度比较高，所以我没有简单用固定宽度三列。宽屏保持三栏效率，中屏把预览放到下一行，窄屏改成单列。这样保留信息结构，同时避免文本和卡片在小窗口下互相挤压。

### 问题 5：为什么没有完成浏览器截图级验证？

#### S - Situation 背景

前端 UI 理想上应该用真实浏览器检查截图、控制台和响应式布局。本阶段尝试使用 Node REPL / Playwright 能力时，当前 Windows 沙箱返回 `CreateProcessAsUserW failed: 5`。

#### T - Task 任务

需要在浏览器自动化能力不可用时，仍完成可执行的前端验收，并诚实记录验证缺口。

#### A - Action 行动

执行 `pnpm build` 进行类型和生产构建验证；临时启动 Vite dev server 并请求 `/workspace`，确认页面路由可访问；未伪造截图或控制台检查结果。

#### R - Result 结果

构建和 HTTP 访问验证通过。截图级和控制台级验证未完成，作为剩余验证风险记录。

#### 技术细节

- 构建命令：`corepack pnpm build`。
- HTTP 验证：临时 `pnpm dev --host 127.0.0.1` 后访问 `/workspace` 返回 200。
- 未完成项：真实浏览器截图、控制台错误检查、移动视口截图。

#### 面试表达

我会区分“构建通过”和“浏览器视觉验证通过”。这次环境限制导致截图级验证没跑通，所以没有假装完成。实际项目里 UI 合并前还应该补浏览器截图、控制台和移动视口检查。

## 4. 技术取舍

- 使用 mock 数据而不是直接绑定后端：保证第三阶段聚焦 UI 和信息架构，避免被未完成的 Agent/AI 流程阻塞。
- 工作台采用四区布局而不是单页聊天框：更符合“可解释的仓库分析流程”定位。
- 使用 Naive UI 按需注册而不是全量注册：减少主包体积，同时保证组件在运行时正确渲染。
- Markdown 预览使用 mock 结构化内容，不接入真实 AI 文档：避免把占位内容包装成真实 AI 产物。
- 通过 CSS Grid + 断点控制响应式，而不是在模板里写多套布局：保持实现简单，后续可继续抽组件。

## 5. 面试可讲点

- 为什么 AI 分析产品不应该只有聊天框？
- 如何设计“文件树 + Agent 步骤 + 工具日志 + Markdown 预览”的信息架构？
- 为什么 UI 阶段先使用 mock 数据？
- Naive UI 全量注册和按需注册有什么差异？
- 如何处理高信息密度工作台的响应式布局？

## 6. 相关 ADR

- `docs/adr/007-为什么第三阶段先使用前端mock数据.md`
