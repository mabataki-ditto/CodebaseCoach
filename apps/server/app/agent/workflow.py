from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import TypeVar

from app.agent.prompts import REAL_DOCUMENT_PROMPTS, build_analysis_context
from app.core.config import settings
from app.core.errors import AppError
from app.schemas.agent import AgentStep, AnalyzeRepoResponse, CoreFileSummary, ToolCallLog
from app.schemas.metrics import MockAnalysisMetrics, RepoOperationMetrics
from app.schemas.repo import BasicFileSummary, RepoParseResponse
from app.services.doc_storage_service import save_markdown_documents
from app.services.file_selector_service import select_core_files_with_metrics
from app.services.file_tree_service import build_file_tree, read_basic_files
from app.services.github_service import clone_repository
from app.services.llm_call_service import LLMCallService
from app.services.llm_service import DEFAULT_PROVIDER, generate_markdown_documents, has_openai_credentials
from app.services.metrics_service import build_mock_analysis_metrics, record_repo_operation_metrics
from app.services.repo_parser import parse_github_repo_url

T = TypeVar("T")


def run_codebase_analysis_workflow(repo_url: str) -> AnalyzeRepoResponse:
    return _run_codebase_analysis_workflow(repo_url=repo_url, force_mock=False)


def run_mock_codebase_analysis_workflow(repo_url: str) -> AnalyzeRepoResponse:
    return _run_codebase_analysis_workflow(repo_url=repo_url, force_mock=True)


def _run_codebase_analysis_workflow(*, repo_url: str, force_mock: bool) -> AnalyzeRepoResponse:
    analysis_started_at = datetime.now(UTC)
    analysis_started = perf_counter()
    steps: list[AgentStep] = []
    tool_logs: list[ToolCallLog] = []

    parsed_repo = _run_stage(
        steps=steps,
        tool_logs=tool_logs,
        title="解析 GitHub URL",
        description="从仓库地址中提取 owner、repo，并规范化 .git 后缀。",
        tool_name="parse_github_repo_url",
        input_summary=repo_url,
        action=lambda: parse_github_repo_url(repo_url),
        output_summary=lambda result: f"{result.owner}/{result.repo}",
    )

    local_path = _run_stage(
        steps=steps,
        tool_logs=tool_logs,
        title="克隆公开仓库",
        description="使用 GitPython 浅克隆仓库到 temp_repos 目录。",
        tool_name="clone_repository",
        input_summary=parsed_repo.repo_url,
        action=lambda: clone_repository(parsed_repo, settings.temp_repo_path),
        output_summary=lambda result: result.name,
    )

    file_tree = _run_stage(
        steps=steps,
        tool_logs=tool_logs,
        title="生成目录树",
        description="过滤依赖、构建产物、缓存和 Git 元数据后生成目录结构。",
        tool_name="build_file_tree",
        input_summary=str(local_path),
        action=lambda: build_file_tree(
            local_path,
            max_depth=settings.max_file_tree_depth,
            max_entries=settings.max_file_tree_entries,
        ),
        output_summary=lambda result: f"返回 {len(result)} 个顶层节点",
    )

    basic_files = _run_stage(
        steps=steps,
        tool_logs=tool_logs,
        title="读取基础文件",
        description="读取 README、package.json、requirements.txt、pyproject.toml 等基础文件摘要。",
        tool_name="read_basic_files",
        input_summary=f"max_bytes={settings.max_basic_file_bytes}",
        action=lambda: read_basic_files(local_path, max_bytes=settings.max_basic_file_bytes),
        output_summary=lambda result: f"读取 {len(result)} 个基础文件",
    )

    core_files, selection_metrics = _run_stage(
        steps=steps,
        tool_logs=tool_logs,
        title="筛选核心文件",
        description="按基础文件、入口文件和核心目录规则筛选 5 到 12 个候选文件。",
        tool_name="select_core_files",
        input_summary=f"max_files={settings.max_core_files}, max_bytes={settings.max_core_file_bytes}",
        action=lambda: select_core_files_with_metrics(
            local_path,
            max_files=settings.max_core_files,
            max_bytes=settings.max_core_file_bytes,
        ),
        output_summary=lambda result: f"候选 {result[1].candidate_core_files} 个，选出 {len(result[0])} 个核心文件",
    )

    use_mock = _should_use_mock(force_mock=force_mock)
    llm_call_records: list = []
    if use_mock:
        documents = _run_stage(
            steps=steps,
            tool_logs=tool_logs,
            title="生成 mock Markdown 文档",
            description="MOCK_MODE 开启或未配置 API Key 时，使用本地 mock 生成器保持流程可演示。",
            tool_name="generate_mock_documents",
            input_summary=f"core_files={len(core_files)}, basic_files={len(basic_files)}",
            action=lambda: _build_mock_markdown_documents(parsed_repo, basic_files, core_files),
            output_summary=lambda result: f"生成 {len(result)} 份 mock Markdown",
        )
    else:
        analysis_context = build_analysis_context(
            parsed_repo=parsed_repo,
            basic_files=basic_files,
            core_files=core_files,
        )
        recorder = LLMCallService(provider=DEFAULT_PROVIDER, model=settings.openai_model)
        documents = _run_stage(
            steps=steps,
            tool_logs=tool_logs,
            title="调用 OpenAI 生成 Markdown 文档",
            description="通过 llm_service 统一调用 OpenAI，并要求文档引用已提供的具体文件路径。",
            tool_name="llm_service.generate_markdown_documents",
            input_summary=f"model={settings.openai_model}, docs={len(REAL_DOCUMENT_PROMPTS)}",
            action=lambda: generate_markdown_documents(
                document_prompts=REAL_DOCUMENT_PROMPTS,
                context=analysis_context,
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                recorder=recorder,
            ),
            output_summary=lambda result: f"生成 {len(result)} 份真实 AI Markdown",
        )
        llm_call_records = recorder.records

    saved_documents, docs_dir = _run_stage(
        steps=steps,
        tool_logs=tool_logs,
        title="保存 Markdown 文档",
        description="将 Markdown 文档保存到 generated_docs 目录，前端读取响应内容进行预览。",
        tool_name="save_markdown_documents",
        input_summary=settings.generated_docs_path.as_posix(),
        action=lambda: save_markdown_documents(
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            docs_root=settings.generated_docs_path,
            documents=documents,
        ),
        output_summary=lambda result: result[1],
    )
    analysis_duration_ms = int((perf_counter() - analysis_started) * 1000)
    metrics = build_mock_analysis_metrics(
        selection_metrics=selection_metrics,
        core_files=core_files,
        documents=saved_documents,
        analysis_duration_ms=analysis_duration_ms,
        used_mock_ai=use_mock,
        provider=DEFAULT_PROVIDER,
        model=settings.openai_model,
        prompt_template_count=0 if use_mock else len(REAL_DOCUMENT_PROMPTS),
        llm_call_records=llm_call_records,
    )
    _record_analysis_metrics(
        repo_url=parsed_repo.repo_url,
        owner=parsed_repo.owner,
        repo=parsed_repo.repo,
        started_at=analysis_started_at,
        metrics=metrics,
        mock_mode=use_mock,
    )

    return AnalyzeRepoResponse(
        owner=parsed_repo.owner,
        repo=parsed_repo.repo,
        repo_url=parsed_repo.repo_url,
        file_tree=file_tree,
        basic_files=basic_files,
        core_files=core_files,
        agent_steps=steps,
        tool_logs=tool_logs,
        documents=saved_documents,
        docs_dir=docs_dir,
        metrics=metrics,
        mock_mode=use_mock,
    )


def _run_stage(
    *,
    steps: list[AgentStep],
    tool_logs: list[ToolCallLog],
    title: str,
    description: str,
    tool_name: str,
    input_summary: str,
    action: Callable[[], T],
    output_summary: Callable[[T], str],
) -> T:
    started_at = _now()
    started = perf_counter()
    try:
        result = action()
    except AppError as exc:
        _append_failed_records(steps, tool_logs, title, description, tool_name, input_summary, started_at, started, exc)
        raise
    except Exception as exc:
        app_error = AppError(
            status_code=500,
            code="UNKNOWN_ERROR",
            message="仓库分析流程执行失败",
            detail=str(exc),
        )
        _append_failed_records(
            steps,
            tool_logs,
            title,
            description,
            tool_name,
            input_summary,
            started_at,
            started,
            app_error,
        )
        raise app_error from exc

    ended_at = _now()
    duration_ms = int((perf_counter() - started) * 1000)
    summary = output_summary(result)
    steps.append(
        AgentStep(
            title=title,
            status="success",
            description=description,
            started_at=started_at,
            ended_at=ended_at,
        )
    )
    tool_logs.append(
        ToolCallLog(
            tool_name=tool_name,
            status="success",
            input_summary=input_summary,
            output_summary=summary,
            duration_ms=duration_ms,
            created_at=ended_at,
        )
    )
    return result


def _append_failed_records(
    steps: list[AgentStep],
    tool_logs: list[ToolCallLog],
    title: str,
    description: str,
    tool_name: str,
    input_summary: str,
    started_at: str,
    started: float,
    error: AppError,
) -> None:
    ended_at = _now()
    duration_ms = int((perf_counter() - started) * 1000)
    steps.append(
        AgentStep(
            title=title,
            status="failed",
            description=description,
            started_at=started_at,
            ended_at=ended_at,
            error_message=error.message,
        )
    )
    tool_logs.append(
        ToolCallLog(
            tool_name=tool_name,
            status="failed",
            input_summary=input_summary,
            output_summary="执行失败",
            duration_ms=duration_ms,
            created_at=ended_at,
            error_message=error.detail or error.message,
        )
    )


def _build_mock_markdown_documents(
    parsed_repo: RepoParseResponse,
    basic_files: list[BasicFileSummary],
    core_files: list[CoreFileSummary],
) -> list[tuple[str, str, str]]:
    core_file_lines = _core_file_lines(core_files)
    basic_file_lines = _basic_file_lines(basic_files)
    repo_name = f"{parsed_repo.owner}/{parsed_repo.repo}"

    return [
        (
            "项目概览",
            "01-项目概览.md",
            f"""# {repo_name} 项目概览

> 本文档由 mock 生成器基于仓库目录、基础文件摘要和核心文件摘要拼接生成，未调用真实 AI。

## 项目事实

- 仓库地址：{parsed_repo.repo_url}
- 已读取基础文件：{len(basic_files)} 个
- 已筛选核心文件：{len(core_files)} 个

## 基础文件

{basic_file_lines}

## 核心文件

{core_file_lines}

## 不确定信息

- 默认分支、业务定位和完整运行链路需要真实仓库内容进一步确认。
""",
        ),
        (
            "技术栈分析",
            "02-技术栈分析.md",
            f"""# 技术栈分析

> mock 结果：这里只根据文件名和文件摘要做规则化判断，不代表真实 AI 推理。

## 可确认事实

{_tech_stack_lines(core_files, basic_files)}

## 合理推测

- 如果存在 `package.json`，项目大概率包含 Node.js 生态脚本或依赖。
- 如果存在 `pyproject.toml` 或 `requirements.txt`，项目大概率包含 Python 生态配置。

## 不确定信息

- 具体框架版本、运行命令和部署方式需要继续读取完整配置后确认。
""",
        ),
        (
            "核心模块解析",
            "03-核心模块解析.md",
            f"""# 核心模块解析

> mock 结果：核心模块来自规则筛选的文件路径，不包含真实语义分析。

## 核心文件候选

{core_file_lines}

## 面试讲述角度

- 可以说明系统先用规则收敛上下文，再把有限文件交给后续分析流程。
- 可以强调当前阶段避免一次性读取整个仓库，降低噪声和上下文成本。
""",
        ),
        (
            "核心流程说明",
            "04-核心流程说明.md",
            f"""# 核心流程说明

## 当前 mock 分析流程

1. 解析 GitHub URL：`{parsed_repo.repo_url}`
2. 浅克隆公开仓库到 `temp_repos/`
3. 过滤无关目录并生成文件树
4. 读取基础文件摘要
5. 筛选最多 12 个核心文件
6. 基于摘要生成 mock Markdown
7. 保存到 `generated_docs/`

## 设计边界

- 本阶段不调用 OpenAI。
- 本阶段不引入 LangChain、MCP 或 RAG。
- 本阶段不读取二进制文件。
""",
        ),
        (
            "面试问题与回答",
            "05-面试问题与回答.md",
            f"""# 面试问题与回答

## Q1：为什么要先筛选核心文件？

A：仓库文件很多，直接读取全部文件会带来性能、上下文长度和噪声问题。本项目先用 README、配置文件、入口文件和核心目录规则筛选 5 到 12 个文件，再把摘要交给后续分析。

## Q2：mock 生成和真实 AI 生成有什么区别？

A：mock 生成只根据已读取摘要拼接模板，不做语义推理。真实 AI 生成需要后续接入 LLM 服务，并在 Prompt 中要求引用具体文件路径、区分事实和推测。

## Q3：当前阶段最重要的工程边界是什么？

A：保持流程可演示，但不把 mock 包装成真实 AI；所有生成内容必须写入 `generated_docs/`，并让前端展示文件树、核心文件和 Markdown。
""",
        ),
        (
            "简历描述",
            "06-简历描述.md",
            f"""# 简历描述

## 可复用表达

- 设计并实现 GitHub 仓库 mock 分析流程，支持 URL 解析、浅克隆、文件树生成、核心文件规则筛选和 Markdown 文档落盘。
- 基于 FastAPI 分层架构封装仓库读取、文件筛选和文档存储服务，并通过 Vue 3 + Naive UI 工作台展示 Agent 执行过程。

## 注意

- 以上描述只对应当前 mock 阶段能力，不能表述为已经接入真实 AI。
""",
        ),
        (
            "可贡献PR方向",
            "07-可贡献PR方向.md",
            f"""# 可贡献 PR 方向

## 当前可观察到的方向

- 为核心文件筛选规则增加更多语言生态入口文件。
- 为生成文档增加复制和下载入口。
- 增加历史记录保存，让 `generated_docs/` 与 `data/history.json` 建立关联。

## 不确定信息

- 真实项目的 issue、贡献规范和测试策略需要读取更多仓库文件后确认。
""",
        ),
    ]


def _core_file_lines(core_files: list[CoreFileSummary]) -> str:
    if not core_files:
        return "- 不确定：未筛选到可读核心文件。"
    return "\n".join(
        f"- `{file.path}`（{file.file_type}）：{file.reason}，大小 {file.size} bytes。"
        for file in core_files
    )


def _basic_file_lines(basic_files: list[BasicFileSummary]) -> str:
    if not basic_files:
        return "- 不确定：未读取到 README、package.json、requirements.txt 或 pyproject.toml。"
    return "\n".join(f"- `{file.path}`（{file.file_type}）：大小 {file.size} bytes。" for file in basic_files)


def _tech_stack_lines(core_files: list[CoreFileSummary], basic_files: list[BasicFileSummary]) -> str:
    paths = {file.path.lower() for file in [*core_files, *basic_files]}
    lines: list[str] = []
    if any(path.endswith("package.json") for path in paths):
        lines.append("- `package.json` 存在：可确认包含 Node.js 生态配置。")
    if any(path.endswith("pyproject.toml") for path in paths):
        lines.append("- `pyproject.toml` 存在：可确认包含 Python 项目配置。")
    if any(path.endswith("requirements.txt") for path in paths):
        lines.append("- `requirements.txt` 存在：可确认包含 Python 依赖清单。")
    if any(path.endswith(".vue") for path in paths):
        lines.append("- `.vue` 文件存在：可确认包含 Vue 单文件组件。")
    if any(path.endswith(".ts") or path.endswith(".tsx") for path in paths):
        lines.append("- TypeScript 文件存在：可确认包含 TypeScript 代码。")
    if not lines:
        lines.append("- 不确定：当前摘要不足以判断主要技术栈。")
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _should_use_mock(*, force_mock: bool) -> bool:
    if force_mock:
        return True
    if getattr(settings, "mock_mode", True):
        return True
    return not has_openai_credentials(getattr(settings, "openai_api_key", None))


def _record_analysis_metrics(
    *,
    repo_url: str,
    owner: str,
    repo: str,
    started_at: datetime,
    metrics: MockAnalysisMetrics,
    mock_mode: bool,
) -> None:
    record_repo_operation_metrics(
        RepoOperationMetrics(
            operation="agent_analyze_mock" if mock_mode else "agent_analyze",
            status="success",
            repo_url=repo_url,
            owner=owner,
            repo=repo,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            duration_ms=metrics.analysis_duration_ms,
            candidate_core_files=metrics.candidate_core_files,
            selected_core_files=metrics.selected_core_files,
            read_files=metrics.read_files,
            truncated_files=metrics.truncated_files,
            raw_candidate_chars=metrics.raw_candidate_chars,
            final_context_chars=metrics.final_context_chars,
            context_compression_ratio=metrics.context_compression_ratio,
            mock_doc_count=metrics.mock_doc_count,
            mock_doc_total_chars=metrics.mock_doc_total_chars,
            analysis_duration_ms=metrics.analysis_duration_ms,
            used_mock_ai=metrics.used_mock_ai,
            provider=metrics.provider,
            model=metrics.model,
            llm_call_count=metrics.llm_call_count,
            llm_success_count=metrics.llm_success_count,
            llm_failed_count=metrics.llm_failed_count,
            llm_total_duration_ms=metrics.llm_total_duration_ms,
            generated_doc_count=metrics.generated_doc_count,
            generated_doc_total_chars=metrics.generated_doc_total_chars,
            generated_doc_total_words=metrics.generated_doc_total_words,
            interview_question_count=metrics.interview_question_count,
            referenced_file_path_count=metrics.referenced_file_path_count,
            prompt_template_count=metrics.prompt_template_count,
        ),
        metrics_file=settings.metrics_path,
    )
