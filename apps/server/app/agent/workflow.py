import logging
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, TypeVar

from app.agent.prompts import REAL_DOCUMENT_PROMPTS, build_analysis_context
from app.core.config import settings
from app.core.errors import AppError
from app.schemas.agent import AgentStep, AnalyzeRepoResponse, CoreFileSummary, ToolCallLog
from app.schemas.metrics import CoreFileSelectionMetrics, MockAnalysisMetrics, RepoOperationMetrics, RepoScanMetrics
from app.schemas.repo import BasicFileSummary, RepoParseResponse
from app.services.agent_step_service import AgentStepRecorder
from app.services.analysis_job_service import AnalysisJobService
from app.services.doc_storage_service import create_markdown_docs_dir, save_markdown_document_to_dir, save_markdown_documents
from app.services.file_selector_service import select_core_files_with_metrics
from app.services.file_tree_service import build_file_tree, read_basic_files, scan_repo_metrics
from app.services.github_service import clone_repository
from app.services.llm_call_service import LLMCallService
from app.services.llm_service import DEFAULT_PROVIDER, generate_markdown_documents, has_llm_credentials
from app.services.metrics_service import build_mock_analysis_metrics, record_repo_operation_metrics
from app.services.repo_parser import parse_github_repo_url
from app.services.history_service import add_history_record
from app.services.tool_log_service import record_tool_call

T = TypeVar("T")

logger = logging.getLogger(__name__)


def run_codebase_analysis_workflow(repo_url: str) -> AnalyzeRepoResponse:
    return _run_codebase_analysis_workflow(repo_url=repo_url, force_mock=False)


def run_mock_codebase_analysis_workflow(repo_url: str) -> AnalyzeRepoResponse:
    return _run_codebase_analysis_workflow(repo_url=repo_url, force_mock=True)


def _run_codebase_analysis_workflow(*, repo_url: str, force_mock: bool) -> AnalyzeRepoResponse:
    analysis_started_at = datetime.now(UTC)
    analysis_started = perf_counter()
    steps: list[AgentStep] = []
    tool_logs: list[ToolCallLog] = []
    step_recorder = AgentStepRecorder(steps)
    parsed_repo: RepoParseResponse | None = None
    core_files: list[CoreFileSummary] = []
    repo_scan_metrics = RepoScanMetrics()
    use_mock = _should_use_mock(force_mock=force_mock)
    logger.info("[workflow] 开始分析 | repo_url=%s | mode=%s", repo_url, "mock" if use_mock else "real")

    try:
        parsed_repo = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="parse_repo_url",
        title="解析 GitHub URL",
        description="从仓库地址中提取 owner/repo，并规范化 .git 后缀。",
        tool_name="parse_github_repo_url",
        input_summary=repo_url,
        input_payload={"repo_url": repo_url},
        action=lambda: parse_github_repo_url(repo_url),
        output_summary=lambda result: f"{result.owner}/{result.repo}",
        output_payload=lambda result: {"owner": result.owner, "repo": result.repo, "repo_url": result.repo_url},
        )

        local_path = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="clone_repository",
        title="克隆公开仓库",
        description="使用 GitPython 将公开仓库克隆到 temp_repos 目录。",
        tool_name="clone_repository",
        input_summary=parsed_repo.repo_url,
        input_payload={"repo_url": parsed_repo.repo_url, "temp_repo_dir": str(settings.temp_repo_path)},
        action=lambda: clone_repository(parsed_repo, settings.temp_repo_path),
        output_summary=lambda result: result.name,
        output_payload=lambda result: {"local_path": str(result), "directory": result.name},
        )

        repo_scan_metrics = scan_repo_metrics(local_path)

        file_tree = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="build_file_tree",
        title="生成目录树",
        description="过滤依赖、构建产物、缓存和 Git 元数据后生成目录结构。",
        tool_name="build_file_tree",
        input_summary=str(local_path),
        input_payload={
            "local_path": str(local_path),
            "max_depth": settings.max_file_tree_depth,
            "max_entries": settings.max_file_tree_entries,
        },
        action=lambda: build_file_tree(
            local_path,
            max_depth=settings.max_file_tree_depth,
            max_entries=settings.max_file_tree_entries,
        ),
        output_summary=lambda result: f"返回 {len(result)} 个顶层节点",
        output_payload=lambda result: {"top_level_nodes": len(result)},
        )

        basic_files = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="read_basic_files",
        title="读取基础文件",
        description="读取 README、package.json、requirements.txt、pyproject.toml 等基础文件摘要。",
        tool_name="read_basic_files",
        input_summary=f"max_bytes={settings.max_basic_file_bytes}",
        input_payload={"max_bytes": settings.max_basic_file_bytes},
        action=lambda: read_basic_files(local_path, max_bytes=settings.max_basic_file_bytes),
        output_summary=lambda result: f"读取 {len(result)} 个基础文件",
        output_payload=lambda result: {"read_files": [file.path for file in result]},
        related_files=lambda result: [file.path for file in result],
        )

        core_files, selection_metrics = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="select_core_files",
        title="筛选并读取核心文件",
        description="按基础文件、入口文件和核心目录规则筛选 5 到 12 个候选文件，并读取摘要。",
        tool_name="select_core_files",
        input_summary=f"max_files={settings.max_core_files}, max_bytes={settings.max_core_file_bytes}",
        input_payload={"max_files": settings.max_core_files, "max_bytes": settings.max_core_file_bytes},
        action=lambda: select_core_files_with_metrics(
            local_path,
            max_files=settings.max_core_files,
            max_bytes=settings.max_core_file_bytes,
        ),
        output_summary=lambda result: f"候选 {result[1].candidate_core_files} 个，选出 {len(result[0])} 个核心文件",
        output_payload=lambda result: {
            "candidate_core_files": result[1].candidate_core_files,
            "selected_files": [file.path for file in result[0]],
            "used_for_context": [file.path for file in result[0] if file.used_for_context],
        },
        related_files=lambda result: [file.path for file in result[0]],
        )

        analysis_context = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="build_analysis_context",
        title="构建 AI 分析上下文",
        description="把仓库信息、基础文件摘要和核心文件摘要整理为模型输入上下文。",
        tool_name="build_analysis_context",
        input_summary=f"basic_files={len(basic_files)}, core_files={len(core_files)}",
        input_payload={
            "basic_files": [file.path for file in basic_files],
            "core_files": [file.path for file in core_files],
        },
        action=lambda: build_analysis_context(
            parsed_repo=parsed_repo,
            basic_files=basic_files,
            core_files=core_files,
        ),
        output_summary=lambda result: f"上下文 {len(result)} 字符",
        output_payload=lambda result: {
            "context_chars": len(result),
            "used_for_context": [file.path for file in core_files if file.used_for_context],
        },
        related_files=lambda _: [file.path for file in core_files if file.used_for_context],
        )

        llm_call_records: list = []
        if use_mock:
            _record_skipped_tool(
            step_recorder,
            tool_logs,
            key="generate_real_ai_documents",
            title="调用 LLM 生成 Markdown",
            description="当前为 mock 模式或未配置 LLM API Key，因此跳过真实 AI 调用。",
            tool_name="llm_service.generate_markdown_documents",
            reason="mock 模式启用或缺少 LLM API Key",
            input_payload={"provider": _llm_provider(), "model": _llm_model(), "base_url": _llm_base_url()},
            )
            documents = _run_stage(
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="generate_mock_documents",
            title="生成 mock Markdown 文档",
            description="使用本地 mock 生成器基于已读取文件摘要生成演示文档。",
            tool_name="generate_mock_documents",
            input_summary=f"core_files={len(core_files)}, basic_files={len(basic_files)}",
            input_payload={
                "basic_files": [file.path for file in basic_files],
                "core_files": [file.path for file in core_files],
                "context_chars": len(analysis_context),
            },
            action=lambda: _build_mock_markdown_documents(parsed_repo, basic_files, core_files),
            output_summary=lambda result: f"生成 {len(result)} 份 mock Markdown",
            output_payload=lambda result: {"documents": [filename for _, filename, _ in result]},
            related_files=lambda _: [file.path for file in core_files],
            )
        else:
            _record_skipped_tool(
            step_recorder,
            tool_logs,
            key="generate_mock_documents",
            title="生成 mock Markdown 文档",
            description="已配置真实 AI 调用，因此跳过 mock 文档生成。",
            tool_name="generate_mock_documents",
            reason="真实 AI 模式已启用",
            input_payload={"mock_mode": False},
            )
            recorder = LLMCallService(provider=_llm_provider(), model=_llm_model())
            documents = _run_stage(
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="generate_real_ai_documents",
            title="调用 LLM 生成 Markdown",
            description="通过 llm_service 统一调用 OpenAI-compatible API，并要求文档引用已提供的具体文件路径。",
            tool_name="llm_service.generate_markdown_documents",
            input_summary=f"provider={_llm_provider()}, model={_llm_model()}, docs={len(REAL_DOCUMENT_PROMPTS)}",
            input_payload={"provider": _llm_provider(), "model": _llm_model(), "base_url": _llm_base_url(), "document_count": len(REAL_DOCUMENT_PROMPTS)},
            action=lambda: generate_markdown_documents(
                document_prompts=REAL_DOCUMENT_PROMPTS,
                context=analysis_context,
                api_key=_llm_api_key(),
                model=_llm_model(),
                base_url=_llm_base_url(),
                recorder=recorder,
            ),
            output_summary=lambda result: f"生成 {len(result)} 份真实 AI Markdown",
            output_payload=lambda result: {"documents": [filename for _, filename, _ in result]},
            related_files=lambda _: [file.path for file in core_files],
            )
            llm_call_records = recorder.records

        saved_documents, docs_dir = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="save_markdown_docs",
        title="保存 Markdown 文档",
        description="将 Markdown 文档保存到 generated_docs 目录，前端读取响应内容进行预览。",
        tool_name="save_markdown_documents",
        input_summary=settings.generated_docs_path.as_posix(),
        input_payload={"docs_root": settings.generated_docs_path.as_posix(), "document_count": len(documents)},
        action=lambda: save_markdown_documents(
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            docs_root=settings.generated_docs_path,
            documents=documents,
        ),
        output_summary=lambda result: result[1],
        output_payload=lambda result: {"docs_dir": result[1], "documents": [document.path for document in result[0]]},
        )
        analysis_duration_ms = int((perf_counter() - analysis_started) * 1000)
        metrics = build_mock_analysis_metrics(
        selection_metrics=selection_metrics,
        core_files=core_files,
        documents=saved_documents,
        analysis_duration_ms=analysis_duration_ms,
        used_mock_ai=use_mock,
        provider=_llm_provider(),
        model=_llm_model(),
        prompt_template_count=0 if use_mock else len(REAL_DOCUMENT_PROMPTS),
        llm_call_records=llm_call_records,
        agent_steps=steps,
        tool_logs=tool_logs,
        repo_scan_metrics=repo_scan_metrics,
        )
        _record_analysis_metrics(
        repo_url=parsed_repo.repo_url,
        owner=parsed_repo.owner,
        repo=parsed_repo.repo,
        started_at=analysis_started_at,
        metrics=metrics,
        mock_mode=use_mock,
        )
        _record_history(
            repo_url=parsed_repo.repo_url,
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            status="success",
            started_at=analysis_started_at,
            completed_at=datetime.now(UTC),
            docs_dir=docs_dir,
            core_files_count=len(core_files),
            error_message=None,
            mock_mode=use_mock,
        )
        logger.info(
            "[workflow] 分析完成 | mode=%s | duration_ms=%d | docs=%d",
            "mock" if use_mock else "real",
            analysis_duration_ms,
            len(saved_documents),
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
    except AppError as exc:
        logger.error(
            "[workflow] 分析失败 | repo_url=%s | mode=%s | code=%s | message=%s",
            repo_url,
            "mock" if use_mock else "real",
            exc.code,
            exc.message,
        )
        _record_history(
            repo_url=parsed_repo.repo_url if parsed_repo else repo_url,
            owner=parsed_repo.owner if parsed_repo else "",
            repo=parsed_repo.repo if parsed_repo else "",
            status="failed",
            started_at=analysis_started_at,
            completed_at=datetime.now(UTC),
            docs_dir="",
            core_files_count=len(core_files),
            error_message=exc.detail or exc.message,
            mock_mode=use_mock,
        )
        raise


def _run_stage(
    *,
    step_recorder: AgentStepRecorder,
    tool_logs: list[ToolCallLog],
    key: str,
    title: str,
    description: str,
    tool_name: str,
    input_summary: str,
    input_payload: dict[str, Any],
    action: Callable[[], T],
    output_summary: Callable[[T], str],
    output_payload: Callable[[T], dict[str, Any]],
    related_files: Callable[[T], list[str]] | None = None,
) -> T:
    step = step_recorder.start(
        key=key,
        title=title,
        description=description,
        metadata={"tool_name": tool_name, "input": input_payload},
    )
    logger.info("[stage] 开始：%s", title)
    started = perf_counter()
    try:
        result = action()
    except AppError as exc:
        _append_failed_records(
            step_recorder,
            tool_logs,
            step,
            tool_name,
            input_summary,
            input_payload,
            started,
            exc,
        )
        raise
    except Exception as exc:
        app_error = AppError(
            status_code=500,
            code="UNKNOWN_ERROR",
            message="仓库分析流程执行失败",
            detail=str(exc),
        )
        _append_failed_records(
            step_recorder,
            tool_logs,
            step,
            tool_name,
            input_summary,
            input_payload,
            started,
            app_error,
        )
        raise app_error from exc

    duration_ms = int((perf_counter() - started) * 1000)
    output = output_payload(result)
    related = related_files(result) if related_files else []
    step_recorder.succeed(step, metadata={"output": output, "related_files": related})
    record_tool_call(
        tool_logs,
        tool_name=tool_name,
        status="success",
        input_summary=input_summary,
        output_summary=output_summary(result),
        input_payload=input_payload,
        output_payload=output,
        related_files=related,
        duration_ms=duration_ms,
    )
    logger.info("[stage] 完成：%s | duration_ms=%d", title, duration_ms)
    return result


def _append_failed_records(
    step_recorder: AgentStepRecorder,
    tool_logs: list[ToolCallLog],
    step: AgentStep,
    tool_name: str,
    input_summary: str,
    input_payload: dict[str, Any],
    started: float,
    error: AppError,
) -> None:
    duration_ms = int((perf_counter() - started) * 1000)
    logger.error(
        "[stage] 失败：%s | code=%s | message=%s | duration_ms=%d",
        step.title,
        error.code,
        error.message,
        duration_ms,
    )
    step_recorder.fail(
        step,
        error_message=error.message,
        metadata={"error_code": error.code, "error_detail": error.detail},
    )
    record_tool_call(
        tool_logs,
        tool_name=tool_name,
        status="failed",
        input_summary=input_summary,
        output_summary="执行失败",
        input_payload=input_payload,
        output_payload={"error_code": error.code},
        duration_ms=duration_ms,
        error_message=error.detail or error.message,
    )
    error.agent_steps = list(step_recorder.steps)
    error.tool_logs = tool_logs


def _record_skipped_tool(
    step_recorder: AgentStepRecorder,
    tool_logs: list[ToolCallLog],
    *,
    key: str,
    title: str,
    description: str,
    tool_name: str,
    reason: str,
    input_payload: dict[str, Any],
) -> None:
    logger.info("[stage] 跳过：%s | reason=%s", title, reason)
    step_recorder.skip(
        key=key,
        title=title,
        description=description,
        reason=reason,
        metadata={"tool_name": tool_name, "input": input_payload},
    )
    record_tool_call(
        tool_logs,
        tool_name=tool_name,
        status="skipped",
        input_summary=reason,
        output_summary="已跳过",
        input_payload=input_payload,
        output_payload={"reason": reason},
        duration_ms=0,
        error_message=reason,
    )


def _build_mock_markdown_documents(
    parsed_repo: RepoParseResponse,
    basic_files: list[BasicFileSummary],
    core_files: list[CoreFileSummary],
) -> list[tuple[str, str, str]]:
    repo_name = f"{parsed_repo.owner}/{parsed_repo.repo}"
    basic_lines = _file_lines(basic_files)
    core_lines = _core_file_lines(core_files)
    context_files = ", ".join(f"`{file.path}`" for file in core_files if file.used_for_context) or "不确定"

    return [
        (
            "项目概览",
            "01-项目概览.md",
            f"""# {repo_name} 项目概览

> 本文档由 mock 生成器基于仓库目录、基础文件摘要和核心文件摘要生成，未调用真实 AI。

## 项目事实

- 仓库地址：{parsed_repo.repo_url}
- 已读取基础文件：{len(basic_files)} 个
- 已筛选核心文件：{len(core_files)} 个

## 基础文件

{basic_lines}

## 核心文件

{core_lines}
""",
        ),
        (
            "技术栈分析",
            "02-技术栈分析.md",
            f"""# 技术栈分析

## 可确认事实

{_tech_stack_lines(core_files, basic_files)}

## 不确定信息

- 具体框架版本、运行命令和部署方式需要继续读取完整配置后确认。
""",
        ),
        (
            "核心模块分析",
            "03-核心模块分析.md",
            f"""# 核心模块分析

## 核心文件候选

{core_lines}

## 用于上下文的文件

- {context_files}
""",
        ),
        (
            "核心流程说明",
            "04-核心流程说明.md",
            f"""# 核心流程说明

1. 解析 GitHub URL：`{parsed_repo.repo_url}`
2. 克隆公开仓库到 `temp_repos/`
3. 过滤无关目录并生成文件树
4. 读取基础文件摘要
5. 筛选并读取核心文件
6. 构建分析上下文
7. 生成并保存 Markdown 文档
""",
        ),
        (
            "面试问题与回答",
            "05-面试问题与回答.md",
            """# 面试问题与回答

## Q1：为什么要先筛选核心文件？

A：仓库文件很多，直接读取全部文件会带来性能和上下文成本问题。本项目先用规则筛选核心文件，再生成分析上下文。

## Q2：mock 生成和真实 AI 生成有什么区别？

A：mock 生成只基于已读取摘要拼接模板，不做语义推理。真实 AI 生成会调用 LLM，并要求引用具体文件路径。

## Q3：如何知道哪些文件进入了 AI 上下文？

A：后端在核心文件结构和工具调用日志中都返回 `used_for_context` 文件列表，前端直接展示这些字段。
""",
        ),
        (
            "简历描述",
            "06-简历描述.md",
            """# 简历描述

- 设计并实现 GitHub 仓库分析工作流，支持 URL 解析、仓库克隆、文件树生成、核心文件筛选和 Markdown 文档保存。
- 为 Agent 工作流补充结构化步骤状态和工具调用日志，让分析过程可解释、可复盘。
""",
        ),
        (
            "可贡献 PR 方向",
            "07-可贡献PR方向.md",
            """# 可贡献 PR 方向

- 为核心文件筛选规则增加更多语言生态入口文件。
- 将一次性返回升级为 SSE，让步骤状态实时更新。
- 增加历史记录中的步骤和工具日志回看能力。
""",
        ),
    ]


def _file_lines(files: list[BasicFileSummary]) -> str:
    if not files:
        return "- 不确定：未读取到基础文件。"
    return "\n".join(f"- `{file.path}`（{file.file_type}）：大小 {file.size} bytes" for file in files)


def _core_file_lines(core_files: list[CoreFileSummary]) -> str:
    if not core_files:
        return "- 不确定：未筛选到可读核心文件。"
    return "\n".join(
        f"- `{file.path}`（{file.file_type}）：{file.reason}，大小 {file.size} bytes"
        for file in core_files
    )


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


def _should_use_mock(*, force_mock: bool) -> bool:
    if force_mock:
        return True
    if getattr(settings, "mock_mode", True):
        return True
    return not has_llm_credentials(_llm_api_key())


def _llm_provider() -> str:
    return getattr(settings, "llm_provider", None) or DEFAULT_PROVIDER


def _llm_api_key() -> str | None:
    return getattr(settings, "llm_api_key", None) or getattr(settings, "openai_api_key", None)


def _llm_model() -> str:
    return getattr(settings, "llm_model", None) or getattr(settings, "openai_model", None) or "gpt-4.1-mini"


def _llm_base_url() -> str | None:
    return getattr(settings, "llm_base_url", None)


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
            total_files=metrics.total_files,
            ignored_dirs=metrics.ignored_dirs,
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
            agent_step_count=metrics.agent_step_count,
            agent_success_step_count=metrics.agent_success_step_count,
            agent_failed_step_count=metrics.agent_failed_step_count,
            agent_skipped_step_count=metrics.agent_skipped_step_count,
            tool_call_count=metrics.tool_call_count,
            tool_success_count=metrics.tool_success_count,
            tool_failed_count=metrics.tool_failed_count,
            avg_tool_duration_ms=metrics.avg_tool_duration_ms,
            max_tool_duration_ms=metrics.max_tool_duration_ms,
            total_tool_duration_ms=metrics.total_tool_duration_ms,
        ),
        metrics_file=settings.metrics_path,
    )


def _record_history(
    *,
    repo_url: str,
    owner: str,
    repo: str,
    status: str,
    started_at: datetime,
    completed_at: datetime,
    docs_dir: str,
    core_files_count: int,
    error_message: str | None,
    mock_mode: bool,
) -> None:
    history_path = getattr(settings, "history_path", None)
    if history_path is None:
        return
    add_history_record(
        history_file=history_path,
        repo_url=repo_url,
        owner=owner,
        repo=repo,
        status=status,
        created_at=started_at.isoformat(),
        completed_at=completed_at.isoformat(),
        docs_dir=docs_dir,
        core_files_count=core_files_count,
        error_message=error_message,
        mock_mode=mock_mode,
    )


def run_codebase_analysis_job(
    *,
    job_id: str,
    repo_url: str,
    job_service: AnalysisJobService,
    force_mock: bool = False,
) -> None:
    analysis_started_at = datetime.now(UTC)
    analysis_started = perf_counter()
    steps: list[AgentStep] = []
    tool_logs: list[ToolCallLog] = []
    step_recorder = AgentStepRecorder(steps)
    parsed_repo: RepoParseResponse | None = None
    core_files: list[CoreFileSummary] = []
    repo_scan_metrics = RepoScanMetrics()
    documents: list[tuple[str, str, str]] = []
    saved_documents = []
    docs_dir = ""
    use_mock = _should_use_mock(force_mock=force_mock)

    try:
        job_service.update_status(job_id, "running", mock_mode=use_mock)
        job_service.append_event(job_id, "job_started", {"repo_url": repo_url, "mock_mode": use_mock})

        parsed_repo = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="parse_repo_url",
            title="解析 GitHub URL",
            description="从仓库地址中提取 owner/repo，并规范化 .git 后缀。",
            tool_name="parse_github_repo_url",
            input_summary=repo_url,
            input_payload={"repo_url": repo_url},
            action=lambda: parse_github_repo_url(repo_url),
            output_summary=lambda result: f"{result.owner}/{result.repo}",
            output_payload=lambda result: {"owner": result.owner, "repo": result.repo, "repo_url": result.repo_url},
        )
        job_service.update_status(job_id, "running", owner=parsed_repo.owner, repo=parsed_repo.repo, mock_mode=use_mock)

        local_path = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="clone_repository",
            title="克隆公开仓库",
            description="使用 GitPython 将公开仓库克隆到 temp_repos 目录。",
            tool_name="clone_repository",
            input_summary=parsed_repo.repo_url,
            input_payload={"repo_url": parsed_repo.repo_url, "temp_repo_dir": str(settings.temp_repo_path)},
            action=lambda: clone_repository(parsed_repo, settings.temp_repo_path),
            output_summary=lambda result: result.name,
            output_payload=lambda result: {"local_path": str(result), "directory": result.name},
        )

        repo_scan_metrics = scan_repo_metrics(local_path)

        file_tree = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="build_file_tree",
            title="生成目录树",
            description="过滤依赖、构建产物、缓存和 Git 元数据后生成目录结构。",
            tool_name="build_file_tree",
            input_summary=str(local_path),
            input_payload={
                "local_path": str(local_path),
                "max_depth": settings.max_file_tree_depth,
                "max_entries": settings.max_file_tree_entries,
            },
            action=lambda: build_file_tree(
                local_path,
                max_depth=settings.max_file_tree_depth,
                max_entries=settings.max_file_tree_entries,
            ),
            output_summary=lambda result: f"返回 {len(result)} 个顶层节点",
            output_payload=lambda result: {"top_level_nodes": len(result)},
        )
        job_service.put_artifact(job_id, "file_tree", [node.model_dump() for node in file_tree])

        basic_files = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="read_basic_files",
            title="读取基础文件",
            description="读取 README、package.json、requirements.txt、pyproject.toml 等基础文件摘要。",
            tool_name="read_basic_files",
            input_summary=f"max_bytes={settings.max_basic_file_bytes}",
            input_payload={"max_bytes": settings.max_basic_file_bytes},
            action=lambda: read_basic_files(local_path, max_bytes=settings.max_basic_file_bytes),
            output_summary=lambda result: f"读取 {len(result)} 个基础文件",
            output_payload=lambda result: {"read_files": [file.path for file in result]},
            related_files=lambda result: [file.path for file in result],
        )
        job_service.put_artifact(job_id, "basic_files", [file.model_dump() for file in basic_files])

        core_files, selection_metrics = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="select_core_files",
            title="筛选并读取核心文件",
            description="按基础文件、入口文件和核心目录规则筛选 5 到 12 个候选文件，并读取摘要。",
            tool_name="select_core_files",
            input_summary=f"max_files={settings.max_core_files}, max_bytes={settings.max_core_file_bytes}",
            input_payload={"max_files": settings.max_core_files, "max_bytes": settings.max_core_file_bytes},
            action=lambda: select_core_files_with_metrics(
                local_path,
                max_files=settings.max_core_files,
                max_bytes=settings.max_core_file_bytes,
            ),
            output_summary=lambda result: f"候选 {result[1].candidate_core_files} 个，选出 {len(result[0])} 个核心文件",
            output_payload=lambda result: {
                "candidate_core_files": result[1].candidate_core_files,
                "selected_files": [file.path for file in result[0]],
                "used_for_context": [file.path for file in result[0] if file.used_for_context],
            },
            related_files=lambda result: [file.path for file in result[0]],
        )
        job_service.put_artifact(job_id, "core_files", [file.model_dump() for file in core_files])
        job_service.append_event(
            job_id,
            "stage_completed",
            {
                "key": "repo_loaded",
                "title": "仓库读取完成",
                "file_tree": [node.model_dump() for node in file_tree],
                "basic_files": [file.model_dump() for file in basic_files],
                "core_files": [file.model_dump() for file in core_files],
            },
        )
        _emit_metrics_update(
            job_id=job_id,
            job_service=job_service,
            phase="repo_loaded",
            selection_metrics=selection_metrics,
            repo_scan_metrics=repo_scan_metrics,
            core_files=core_files,
            documents=saved_documents,
            analysis_started=analysis_started,
            use_mock=use_mock,
            llm_call_records=[],
            steps=steps,
            tool_logs=tool_logs,
        )

        analysis_context = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="build_analysis_context",
            title="构建 AI 分析上下文",
            description="把仓库信息、基础文件摘要和核心文件摘要整理为模型输入上下文。",
            tool_name="build_analysis_context",
            input_summary=f"basic_files={len(basic_files)}, core_files={len(core_files)}",
            input_payload={"basic_files": [file.path for file in basic_files], "core_files": [file.path for file in core_files]},
            action=lambda: build_analysis_context(parsed_repo=parsed_repo, basic_files=basic_files, core_files=core_files),
            output_summary=lambda result: f"上下文 {len(result)} 字符",
            output_payload=lambda result: {"context_chars": len(result), "used_for_context": [file.path for file in core_files if file.used_for_context]},
            related_files=lambda _: [file.path for file in core_files if file.used_for_context],
        )

        docs_path, docs_dir = create_markdown_docs_dir(owner=parsed_repo.owner, repo=parsed_repo.repo, docs_root=settings.generated_docs_path)
        job_service.update_status(job_id, "running", docs_dir=docs_dir, core_files_count=len(core_files), mock_mode=use_mock)
        llm_call_records: list = []
        recorder = LLMCallService(provider=_llm_provider(), model=_llm_model())

        if use_mock:
            _record_skipped_tool(
                step_recorder,
                tool_logs,
                key="generate_real_ai_documents",
                title="调用 LLM 生成 Markdown",
                description="当前为 mock 模式或未配置 LLM API Key，因此跳过真实 AI 调用。",
                tool_name="llm_service.generate_markdown_documents",
                reason="mock 模式启用或缺少 LLM API Key",
                input_payload={"provider": _llm_provider(), "model": _llm_model(), "base_url": _llm_base_url()},
            )
            documents = _build_mock_markdown_documents(parsed_repo, basic_files, core_files)
        else:
            _record_skipped_tool(
                step_recorder,
                tool_logs,
                key="generate_mock_documents",
                title="生成 mock Markdown 文档",
                description="已配置真实 AI 调用，因此跳过 mock 文档生成。",
                tool_name="generate_mock_documents",
                reason="真实 AI 模式已启用",
                input_payload={"mock_mode": False},
            )
            documents = []
            for prompt in REAL_DOCUMENT_PROMPTS:
                _raise_if_cancelled(job_id, job_service)
                generated = generate_markdown_documents(
                    document_prompts=[prompt],
                    context=analysis_context,
                    api_key=_llm_api_key(),
                    model=_llm_model(),
                    base_url=_llm_base_url(),
                    recorder=recorder,
                )
                documents.extend(generated)
                saved = save_markdown_document_to_dir(
                    docs_root=settings.generated_docs_path,
                    docs_dir=docs_path,
                    title=generated[0][0],
                    filename=generated[0][1],
                    content=generated[0][2],
                )
                saved_documents.append(saved)
                job_service.put_artifact(job_id, "documents", [document.model_dump() for document in saved_documents])
                job_service.append_event(
                    job_id,
                    "document_generated",
                    {
                        "document": saved.model_dump(),
                        "index": len(saved_documents),
                        "total": len(REAL_DOCUMENT_PROMPTS),
                    },
                )
                _emit_metrics_update(
                    job_id=job_id,
                    job_service=job_service,
                    phase="document_generated",
                    selection_metrics=selection_metrics,
                    repo_scan_metrics=repo_scan_metrics,
                    core_files=core_files,
                    documents=saved_documents,
                    analysis_started=analysis_started,
                    use_mock=use_mock,
                    llm_call_records=recorder.records,
                    steps=steps,
                    tool_logs=tool_logs,
                )
            llm_call_records = recorder.records

        if use_mock:
            for index, (title, filename, content) in enumerate(documents, start=1):
                _raise_if_cancelled(job_id, job_service)
                saved = save_markdown_document_to_dir(
                    docs_root=settings.generated_docs_path,
                    docs_dir=docs_path,
                    title=title,
                    filename=filename,
                    content=content,
                )
                saved_documents.append(saved)
                job_service.put_artifact(job_id, "documents", [document.model_dump() for document in saved_documents])
                job_service.append_event(
                    job_id,
                    "document_generated",
                    {"document": saved.model_dump(), "index": index, "total": len(documents)},
                )
                _emit_metrics_update(
                    job_id=job_id,
                    job_service=job_service,
                    phase="document_generated",
                    selection_metrics=selection_metrics,
                    repo_scan_metrics=repo_scan_metrics,
                    core_files=core_files,
                    documents=saved_documents,
                    analysis_started=analysis_started,
                    use_mock=use_mock,
                    llm_call_records=[],
                    steps=steps,
                    tool_logs=tool_logs,
                )

        analysis_duration_ms = int((perf_counter() - analysis_started) * 1000)
        metrics = build_mock_analysis_metrics(
            selection_metrics=selection_metrics,
            core_files=core_files,
            documents=saved_documents,
            analysis_duration_ms=analysis_duration_ms,
            used_mock_ai=use_mock,
            provider=_llm_provider(),
            model=_llm_model(),
            prompt_template_count=0 if use_mock else len(REAL_DOCUMENT_PROMPTS),
            llm_call_records=llm_call_records,
            agent_steps=steps,
            tool_logs=tool_logs,
            repo_scan_metrics=repo_scan_metrics,
        )
        _record_analysis_metrics(
            repo_url=parsed_repo.repo_url,
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            started_at=analysis_started_at,
            metrics=metrics,
            mock_mode=use_mock,
        )
        _record_history(
            repo_url=parsed_repo.repo_url,
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            status="success",
            started_at=analysis_started_at,
            completed_at=datetime.now(UTC),
            docs_dir=docs_dir,
            core_files_count=len(core_files),
            error_message=None,
            mock_mode=use_mock,
        )
        response = AnalyzeRepoResponse(
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
        job_service.put_artifact(job_id, "result", response.model_dump())
        job_service.update_status(job_id, "success", docs_dir=docs_dir, core_files_count=len(core_files), metrics=metrics, mock_mode=use_mock)
        job_service.append_event(job_id, "metrics_updated", {"phase": "completed", "metrics": metrics.model_dump()})
        job_service.append_event(job_id, "job_completed", {"result": response.model_dump(), "metrics": metrics.model_dump(), "docs_dir": docs_dir})
    except _AnalysisJobCancelled:
        job_service.update_status(job_id, "cancelled", docs_dir=docs_dir, core_files_count=len(core_files), error_message="用户停止分析", mock_mode=use_mock)
        job_service.append_event(job_id, "job_cancelled", {"message": "用户停止分析", "documents": [document.model_dump() for document in saved_documents]})
        if parsed_repo is not None:
            _record_history(
                repo_url=parsed_repo.repo_url,
                owner=parsed_repo.owner,
                repo=parsed_repo.repo,
                status="cancelled",
                started_at=analysis_started_at,
                completed_at=datetime.now(UTC),
                docs_dir=docs_dir,
                core_files_count=len(core_files),
                error_message="用户停止分析",
                mock_mode=use_mock,
            )
    except AppError as exc:
        job_service.update_status(job_id, "failed", docs_dir=docs_dir, core_files_count=len(core_files), error_message=exc.detail or exc.message, mock_mode=use_mock)
        job_service.append_event(job_id, "job_failed", {"code": exc.code, "message": exc.message, "detail": exc.detail, "documents": [document.model_dump() for document in saved_documents]})
        _record_history(
            repo_url=parsed_repo.repo_url if parsed_repo else repo_url,
            owner=parsed_repo.owner if parsed_repo else "",
            repo=parsed_repo.repo if parsed_repo else "",
            status="failed",
            started_at=analysis_started_at,
            completed_at=datetime.now(UTC),
            docs_dir=docs_dir,
            core_files_count=len(core_files),
            error_message=exc.detail or exc.message,
            mock_mode=use_mock,
        )
    except Exception as exc:
        logger.exception("[analyze-job] unexpected failure | job_id=%s | repo_url=%s", job_id, repo_url)
        message = str(exc) or "Unexpected analysis failure"
        job_service.update_status(
            job_id,
            "failed",
            docs_dir=docs_dir,
            core_files_count=len(core_files),
            error_message=message,
            mock_mode=use_mock,
        )
        job_service.append_event(
            job_id,
            "job_failed",
            {
                "code": "ANALYSIS_JOB_FAILED",
                "message": "Analysis failed",
                "detail": message,
                "documents": [document.model_dump() for document in saved_documents],
            },
        )
        _record_history(
            repo_url=parsed_repo.repo_url if parsed_repo else repo_url,
            owner=parsed_repo.owner if parsed_repo else "",
            repo=parsed_repo.repo if parsed_repo else "",
            status="failed",
            started_at=analysis_started_at,
            completed_at=datetime.now(UTC),
            docs_dir=docs_dir,
            core_files_count=len(core_files),
            error_message=message,
            mock_mode=use_mock,
        )


class _AnalysisJobCancelled(Exception):
    pass


def _raise_if_cancelled(job_id: str, job_service: AnalysisJobService) -> None:
    if job_service.is_cancel_requested(job_id):
        raise _AnalysisJobCancelled()


def _run_job_stage(
    *,
    job_id: str,
    job_service: AnalysisJobService,
    step_recorder: AgentStepRecorder,
    tool_logs: list[ToolCallLog],
    key: str,
    title: str,
    description: str,
    tool_name: str,
    input_summary: str,
    input_payload: dict[str, Any],
    action: Callable[[], T],
    output_summary: Callable[[T], str],
    output_payload: Callable[[T], dict[str, Any]],
    related_files: Callable[[T], list[str]] | None = None,
) -> T:
    _raise_if_cancelled(job_id, job_service)
    job_service.append_event(job_id, "stage_started", {"key": key, "title": title, "description": description})
    try:
        result = _run_stage(
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key=key,
            title=title,
            description=description,
            tool_name=tool_name,
            input_summary=input_summary,
            input_payload=input_payload,
            action=action,
            output_summary=output_summary,
            output_payload=output_payload,
            related_files=related_files,
        )
    except AppError as exc:
        job_service.append_event(job_id, "stage_failed", {"key": key, "title": title, "code": exc.code, "message": exc.message, "detail": exc.detail})
        raise
    job_service.append_event(job_id, "stage_completed", {"key": key, "title": title, "output": output_payload(result)})
    _raise_if_cancelled(job_id, job_service)
    return result


def _emit_metrics_update(
    *,
    job_id: str,
    job_service: AnalysisJobService,
    phase: str,
    selection_metrics: CoreFileSelectionMetrics,
    repo_scan_metrics: RepoScanMetrics,
    core_files: list[CoreFileSummary],
    documents: list,
    analysis_started: float,
    use_mock: bool,
    llm_call_records: list,
    steps: list[AgentStep],
    tool_logs: list[ToolCallLog],
) -> None:
    metrics = build_mock_analysis_metrics(
        selection_metrics=selection_metrics,
        repo_scan_metrics=repo_scan_metrics,
        core_files=core_files,
        documents=documents,
        analysis_duration_ms=int((perf_counter() - analysis_started) * 1000),
        used_mock_ai=use_mock,
        provider=_llm_provider(),
        model=_llm_model(),
        prompt_template_count=0 if use_mock else len(REAL_DOCUMENT_PROMPTS),
        llm_call_records=llm_call_records,
        agent_steps=steps,
        tool_logs=tool_logs,
    )
    job_service.append_event(job_id, "metrics_updated", {"phase": phase, "metrics": metrics.model_dump()})
