# 阶段 5：OpenAI SDK 接入和真实文档生成复盘

## 1. 本阶段目标

- 接入 OpenAI Python SDK，通过 `.env` 读取 `OPENAI_API_KEY` 和 `OPENAI_MODEL`。
- 封装 `app/services/llm_service.py`，所有 OpenAI 调用集中在此。
- 将 Prompt 统一放入 `app/agent/prompts.py`，不散落在路由函数里。
- 实现真实 AI 生成 7 份 Markdown 文档（项目概览、技术栈分析、核心模块解析、核心流程说明、面试问题与回答、简历描述、可贡献 PR 方向）。
- 没有 API Key 时自动回退到第四阶段的 mock 模式，保证演示链路不中断。
- AI 调用失败时返回结构化错误，不让前端崩溃。
- Prompt 必须要求模型引用具体文件路径、不编造未提供的文件、信息不足写「不确定」、面向前端开发者、面向实习面试准备、区分事实/推测/建议。

本阶段不引入 LangChain、MCP、RAG，也不实现历史记录持久化。

## 2. 实际完成内容

- 在 `app/services/llm_service.py` 封装 OpenAI 调用，对外暴露 `has_openai_credentials` 和 `generate_markdown_documents`，内部用 `client.responses.create` 完成 7 份文档的独立请求。
- 在 `app/agent/prompts.py` 沉淀 `SYSTEM_PROMPT`（6 条全局约束）和 `REAL_DOCUMENT_PROMPTS`（7 个 `DocumentPrompt` dataclass），并通过 `build_analysis_context` 把仓库信息、基础文件摘要、核心文件摘要拼成上下文字符串。
- 在 `app/agent/workflow.py` 接入真实 AI 分支：`_should_use_mock` 做三级判定（`force_mock` > `settings.mock_mode` > `has_openai_credentials`），决定走 mock 还是真实 LLM。
- 在 `app/core/config.py` 保留 `openai_api_key`、`openai_model`、`mock_mode` 字段，`.env.example` 同步示例。
- 在 `app/api/agent.py` 暴露 `POST /api/agent/analyze`（真实）和 `POST /api/agent/analyze/mock`（强制 mock）两个入口，前端 `api/analysis.ts` 均已接入。
- 定义 4 个结构化错误码：`OPENAI_API_KEY_MISSING`（400）、`LLM_DEPENDENCY_MISSING`（500）、`LLM_CALL_FAILED`（502）、`LLM_EMPTY_RESPONSE`（502）。
- 对 OpenAI 异常信息做 API Key 脱敏（`_safe_error_detail`），避免凭据泄漏到前端。
- 新增 `tests/test_llm_service.py` 覆盖 `has_openai_credentials` 和 `_safe_error_detail`；在 `tests/test_agent_workflow_metrics.py` 新增 3 个用例覆盖真实 AI 分支（无 Key 回退、有 Key 走 LLM、LLM 失败返回结构化错误）。
- 新增 `docs/adr/010-使用OpenAI-Responses-API生成文档.md`，记录接口选型决策。

## 3. 遇到的问题与解决方案

### 问题 1：选择 OpenAI Responses API 还是 Chat Completions API

#### S - Situation 背景

第五阶段要接入真实 AI，OpenAI Python SDK 同时支持传统的 Chat Completions 和较新的 Responses API。项目 Prompt 结构是「统一系统约束 + 每份文档独立指令」，需要选一套接口承载。

#### T - Task 任务

在不引入复杂 Agent 框架的前提下，选一个能分离系统约束与文档指令、能直接限制输出长度、且后续可扩展的接口。

#### A - Action 行动

选择 Responses API。在 `llm_service.py:_generate_single_document` 用 `instructions=SYSTEM_PROMPT` 传全局约束，`input=文档指令 + 上下文` 传每份文档的内容，`max_output_tokens=1800` 限制单份文档长度。同时实现 `_extract_output_text`，先读 `response.output_text`，再遍历 `response.output[].content[].text`，兼容不同 SDK 版本的返回结构。

#### R - Result 结果

7 份文档各自独立请求，单份失败不影响其他文档的错误隔离。本地 venv `openai==2.44.0` 实测可用，22 个后端单元测试通过。

#### 技术细节

- 调用位置：`app/services/llm_service.py:62-67`。
- 默认输出上限：`DEFAULT_MAX_OUTPUT_TOKENS = 1800`。
- 响应解析：`_extract_output_text` 双路兜底。
- 7 份文档通过 `for prompt in document_prompts` 循环独立请求，每次调用都带完整 `SYSTEM_PROMPT`。
- 依赖声明：`requirements.txt` 写 `openai>=1.0.0`，下限偏宽，详见 ADR-010 的「代价」一节。

#### 面试表达

我没有用最常见的 Chat Completions，而是选了 Responses API，因为它用 `instructions` 和 `input` 分离系统约束与用户输入，刚好对应我「全局 Prompt + 每份文档独立指令」的双层结构。同时做了响应解析的兜底，兼容不同 SDK 版本的返回格式，避免升级 SDK 时整块崩。

### 问题 2：无 API Key 时如何安全回退到 mock

#### S - Situation 背景

产品要求「无 Key 可演示，有 Key 走真实 AI」，同时默认不能意外消耗 API 费用。第四阶段已经有完整的 mock 生成器，第五阶段需要在它之上加一个判定层。

#### T - Task 任务

设计一个清晰、可测试的判定逻辑，区分三种情况：强制 mock、默认 mock、有 Key 走真实 AI。同时要防止 `.env.example` 里的占位符 `your_api_key_here` 被误判为真实 Key。

#### A - Action 行动

在 `workflow.py:_should_use_mock` 实现三级优先判定：
1. `force_mock=True` → 直接走 mock（对应 `/api/agent/analyze/mock` 入口）。
2. `settings.mock_mode=True` → 走 mock（默认值，保证开箱即用不烧钱）。
3. 否则看 `has_openai_credentials`：返回 `False` 则走 mock。

`has_openai_credentials` 在 `llm_service.py` 里拒绝 `None`、空串和占位符 `your_api_key_here`，只有真正非空非占位的 Key 才返回 `True`。

#### R - Result 结果

用户必须显式设置 `MOCK_MODE=false` 且提供真实 Key 才会走真实 AI，默认行为永远是 mock。3 个单元测试覆盖三种路径：`test_analysis_falls_back_to_mock_when_api_key_is_missing`、`test_analysis_uses_llm_service_when_api_key_is_configured`、`test_analysis_returns_structured_error_when_llm_fails`。

#### 技术细节

- 判定函数：`app/agent/workflow.py:465-470`。
- 凭据校验：`app/services/llm_service.py:17-21`。
- 测试通过 monkey-patch `workflow.generate_markdown_documents` 替换为 `_fail_if_called` / `_fake_markdown_documents` / `_raise_llm_error`，隔离真实网络调用。
- 响应字段 `mock_mode: bool` 让前端能区分本次文档来自 mock 还是真实 AI。

#### 面试表达

我把 mock 判定做成三级优先级，默认 `MOCK_MODE=true` 保证开箱即用、不会意外烧 API 费用；用户要显式关掉 mock 才走真实 AI。同时排除了 `.env.example` 里的占位符被误判为真 Key。测试用 monkey-patch 替换 LLM 调用，三种路径都能在不联网的情况下验证。

### 问题 3：OpenAI 异常信息中的 API Key 脱敏

#### S - Situation 背景

OpenAI 调用失败时，异常对象的字符串形式可能包含请求里带的 API Key。错误信息需要返回给前端帮助排查，但不能泄漏凭据。

#### T - Task 任务

在错误信息透传到前端之前，确保任何形式的 Key 都被替换掉，同时保留足够的信息用于排查。

#### A - Action 行动

在 `llm_service.py:_safe_error_detail` 做双重脱敏：
1. 先把异常字符串截断到 500 字符，避免超长错误信息。
2. 替换传入的 `api_key` 字符串为 `[redacted-openai-key]`。
3. 再用正则 `sk-[A-Za-z0-9_-]{20,}` 兜底替换未知格式的 Key。

#### R - Result 结果

测试 `test_safe_error_detail_redacts_openai_keys` 验证：包含真实 Key 的异常信息脱敏后不再包含原 Key，且包含 `[redacted-openai-key]` 标记。

#### 技术细节

- 函数：`app/services/llm_service.py:103-107`。
- 截断长度：500 字符。
- 正则：`sk-[A-Za-z0-9_-]{20,}`，覆盖标准 OpenAI Key 前缀格式。
- 错误码 `LLM_CALL_FAILED` 的 `detail` 字段统一经过此函数处理。

#### 面试表达

错误信息要可排查又要安全，我对 OpenAI 异常做了双重脱敏——既替换已知 Key 字符串，又用正则兜底未知 Key 格式。这样前端展示错误细节时不会泄漏凭据，同时保留了异常类型和大致信息供后端排查。

## 4. 技术取舍

- **Responses API 优于 Chat Completions**：贴合双层 Prompt 结构，`max_output_tokens` 语义清晰。代价是对 SDK 版本有隐性要求，详见 ADR-010。
- **7 份文档独立请求而非一次生成**：单份失败可隔离、单份返回更快、Prompt 更聚焦；代价是总 token 成本和耗时高于一次生成 7 份。MVP 阶段优先稳定性和错误隔离。
- **mock 判定放 workflow 层而非 llm_service 层**：`llm_service` 只关心「有 Key 就调」，是否调由 workflow 决定。这样 `llm_service` 职责单一，mock 分支复用第四阶段已有生成器。
- **Prompt 用 dataclass 而非散字符串**：`DocumentPrompt(title, filename, instruction)` 把文档元信息和指令绑在一起，workflow 直接遍历生成，避免指令和文件名错配。
- **测试用 monkey-patch 隔离网络**：不引入 `responses` 或 `httpx-mock` 等额外依赖，直接替换 `workflow.generate_markdown_documents`，验证的是 workflow 的分支逻辑而非 OpenAI SDK 本身。
- **错误码细分 4 种**：让前端能区分「没配 Key」「SDK 没装」「调用失败」「空响应」，对应不同的用户提示。

## 5. 面试可讲点

- 为什么选 Responses API 而不是 Chat Completions？两层 Prompt 结构如何映射到 `instructions` / `input`？
- 无 API Key 时的三级回退判定是怎么设计的？为什么默认 `MOCK_MODE=true`？
- OpenAI 异常里的 API Key 如何脱敏？为什么要双重脱敏（字符串替换 + 正则兜底）？
- 7 份文档为什么独立请求而不是一次生成？错误隔离和 token 成本如何权衡？
- 真实 AI 分支的测试如何在不联网的情况下覆盖？为什么选 monkey-patch 而不是 mock 库？
- Prompt 如何强制模型「引用文件路径、不编造、区分事实/推测/建议」？这些约束放在 `SYSTEM_PROMPT` 还是每个文档指令里？

## 6. 相关 ADR

- `docs/adr/010-使用OpenAI-Responses-API生成文档.md`
