# CodebaseCoach Server

FastAPI 后端骨架。

## 启动

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 接口

- `GET /health`
- `POST /api/repo/parse`
- `POST /api/repo/scan`

当前阶段已实现 GitHub URL 解析、公开仓库浅克隆、基础目录树和基础文件摘要读取。不实现 AI 调用和最终文档生成。
