# CodebaseCoach

CodebaseCoach 是一个面向前端开发者和 AI 应用开发实习求职者的开源项目学习与面试准备工具。

当前阶段只完成项目基础结构和前后端骨架：

- Vue 3 + TypeScript + Vite 前端
- Naive UI 基础接入
- FastAPI 后端
- `/health` 健康检查接口
- 首页、分析工作台、文档页、历史记录页、设置页骨架

## 目录结构

```text
apps/
  web/      # Vue 前端
  server/   # FastAPI 后端
docs/       # 产品文档与阶段复盘
generated_docs/
temp_repos/
data/
```

## 前端启动

```bash
cd apps/web
pnpm install
pnpm dev
```

前端默认运行在 `http://localhost:5173`。

## 后端启动

```bash
cd apps/server
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

## 当前边界

第一阶段不实现真实 AI 调用、不实现 GitHub clone、不引入 LangChain、MCP、RAG，也不会在前端保存或展示 API Key。
