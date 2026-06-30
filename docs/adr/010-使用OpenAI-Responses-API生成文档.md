# ADR-010：使用 OpenAI Responses API 生成项目文档

## 背景

第五阶段需要接入 OpenAI Python SDK 生成 7 份 Markdown 文档。OpenAI SDK 同时提供两套主流文本生成接口：

- Chat Completions API（`client.chat.completions.create`）：传统接口，通过 `messages` 列表传入 system / user / assistant 消息。
- Responses API（`client.responses.create`）：较新的统一接口，通过 `instructions` 和 `input` 字段分离系统约束与用户输入，并支持 `max_output_tokens` 直接限制输出长度。

本项目的 Prompt 结构是「统一系统约束 + 每份文档独立指令」，需要选择一套接口承载。

## 备选方案

### 方案 A：Chat Completions API

- 用 `messages=[{"role":"system",...},{"role":"user",...}]` 传 SYSTEM_PROMPT 和文档指令。
- 生态最成熟，文档示例最多。
- 限制输出长度需要靠 `max_tokens`（已逐步被 `max_completion_tokens` 取代）。

### 方案 B：Responses API

- 用 `instructions=SYSTEM_PROMPT`、`input=文档指令 + 上下文` 分离两层 Prompt。
- `max_output_tokens` 直接控制输出 token 数，语义清晰。
- 是 OpenAI 推荐的统一接口方向，后续工具调用、结构化输出能力更一致。

## 决策

选择方案 B，使用 Responses API。

核心调用形态见 `app/services/llm_service.py:_generate_single_document`：

```python
response = client.responses.create(
    model=model,
    instructions=SYSTEM_PROMPT,
    input=f"{prompt}\n\n# 已读取的仓库上下文\n\n{context}",
    max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
)
```

## 原因

1. **贴合双层 Prompt 结构**：项目把「全局约束」（引用文件路径、不编造、区分事实/推测/建议等）放进 `SYSTEM_PROMPT`，把「每份文档的结构建议」放进 `DocumentPrompt.instruction`。`instructions` / `input` 的分离天然对应这两层，不必拼成 messages 数组。

2. **输出长度控制语义清晰**：`max_output_tokens` 直接限制模型输出，配合 `DEFAULT_MAX_OUTPUT_TOKENS=1800` 防止单份文档失控，比 `max_tokens` 更直白。

3. **统一接口方向**：Responses API 是 OpenAI 推荐的统一入口，后续若要扩展工具调用或结构化输出，迁移成本更低。

## 代价

1. **对 SDK 版本有隐性要求**：Responses API 需要较新版本的 `openai` 包。当前 `requirements.txt` 写的是 `openai>=1.0.0`，下限偏宽——实际运行需要支持 `responses.create` 的版本（本地 venv 实测 2.44.0 可用）。后续应把下限收紧到支持 Responses API 的最低版本，避免用户装到旧版时报 `AttributeError`。

2. **响应解析需要兜底**：不同 SDK 版本返回结构略有差异。`_extract_output_text` 先读 `response.output_text`，再遍历 `response.output[].content[].text`，增加了一点解析代码。

3. **生态示例相对少**：社区大部分教程仍以 Chat Completions 为主，遇到问题时可参考资料较少。

## 结果

- `llm_service.py` 通过 `client.responses.create` 完成真实 AI 调用，7 份文档各自独立请求。
- 无 API Key 时由 `workflow._should_use_mock` 回退到 mock 生成器，链路不中断。
- 后端 22 个单元测试通过，其中 3 个直接覆盖真实 AI 分支（无 Key 回退、有 Key 走 LLM、LLM 失败返回结构化错误）。
- 本地 venv `openai==2.44.0` 实测可用。
