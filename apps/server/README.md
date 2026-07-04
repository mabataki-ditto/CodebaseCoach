# CodebaseCoach Server

FastAPI backend for reading GitHub repositories, selecting core files, generating LLM Markdown documents, and recording history/metrics.

## Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## LLM Configuration

The server requires a real OpenAI-compatible LLM configuration. If the key is missing or still uses a placeholder value, analysis fails with `LLM_API_KEY_MISSING`.

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=your_deepseek_api_key
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
```

`OPENAI_API_KEY` and `OPENAI_MODEL` are kept as compatibility fields; `LLM_*` takes priority.

## API

- `GET /health`
- `POST /api/repo/parse`
- `POST /api/repo/scan`
- `POST /api/agent/analyze`
- `GET /api/history`
- `DELETE /api/history/{record_id}`
- `GET /api/docs/{history_id}`
