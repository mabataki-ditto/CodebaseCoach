# ADR-003：FastAPI 后端采用分层骨架

## 背景

第一阶段后端只需要 `/health` 接口，但后续会加入 GitHub URL 解析、仓库 clone、文件树生成、核心文件筛选、基础文件读取、AI 调用封装、Markdown 文档保存、历史记录保存和结构化错误返回。

如果第一阶段把所有逻辑都放进 `main.py`，后续阶段会快速变成单文件堆叠，难以测试和维护。

## 备选方案

### 方案 A：FastAPI 分层目录

按职责拆分为 `main.py`、`api`、`schemas`、`services`、`agent`、`core`、`utils`。

优点是后续能力有明确归属，`main.py` 可以保持薄入口，路由、数据模型、业务服务和 Agent 工作流可以逐步补齐。缺点是第一阶段会出现一些空模块，对极小 demo 来说目录数量偏多。

### 方案 B：单文件 FastAPI

所有接口、配置和业务逻辑都写在 `app/main.py`。

优点是初始文件最少，健康检查实现最快。缺点是与“不要把所有后端逻辑写进 main.py”的约束冲突，也不适合后续仓库分析和 AI 调用扩展。

### 方案 C：第一阶段直接实现完整服务层

第一阶段就把 repo、agent、docs、history 的接口和 service 全部写完。

优点是结构看起来更完整。缺点是明显跨阶段，会引入未验证的业务逻辑和依赖，增加返工风险。

## 决策

采用 FastAPI 分层骨架，但第一阶段只实现必要逻辑：

- `app/main.py`：创建 FastAPI app、配置 CORS、注册 router。
- `app/api/health.py`：实现 `/health`。
- `app/schemas/health.py`：定义健康检查响应模型。
- `app/core/config.py`：读取基础配置。
- `api`、`schemas`、`services`、`agent` 中的其他文件只作为后续阶段结构预留。

## 原因

这个方案在可运行和可扩展之间保持平衡。它避免了单文件入口膨胀，也没有提前实现真实仓库分析或 AI 调用。

FastAPI 与 Pydantic 适合后续沉淀结构化 API 合约，符合产品要求的结构化错误和请求响应模型设计方向。

## 代价

- 第一阶段存在空文件，需要在后续阶段逐步填充。
- 需要持续维护分层边界，避免 API 路由层直接读写文件或调用模型。
- 后续需要补测试来验证 route、schema、service 的协作。

## 结果

当前后端已实现 `GET /health`、CORS 配置、`HealthResponse` 响应模型和基础 Settings 配置。`python -m compileall app` 与 Uvicorn 临时启动验证均已通过。
