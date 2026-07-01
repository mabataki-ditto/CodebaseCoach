# CodebaseCoach Server

FastAPI 后端服务，负责 GitHub 仓库读取、核心文件筛选、LLM 文档生成、历史记录和指标记录。

## 启动

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## LLM 配置

默认 `MOCK_MODE=true`，不会调用真实模型。要调用真实 OpenAI-compatible API，配置 `.env`：

```env
MOCK_MODE=false
LLM_PROVIDER=openai
LLM_API_KEY=your_llm_api_key_here
LLM_MODEL=gpt-4.1-mini
LLM_BASE_URL=
```

DeepSeek 示例：

```env
MOCK_MODE=false
LLM_PROVIDER=deepseek
LLM_API_KEY=your_deepseek_api_key
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
```

`OPENAI_API_KEY` 和 `OPENAI_MODEL` 暂时保留为兼容字段；新配置优先使用 `LLM_*`。

## 接口

- `GET /health`
- `POST /api/repo/parse`
- `POST /api/repo/scan`
- `POST /api/agent/analyze`
- `POST /api/agent/analyze/mock`
- `GET /api/history`
- `DELETE /api/history/{record_id}`
- `GET /api/docs/{history_id}`
