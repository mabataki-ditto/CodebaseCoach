import logging
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, TypeVar

from app.agent.prompts import REAL_DOCUMENT_PROMPTS, build_analysis_context
from app.agent.tools import assert_tool_allowed
from app.core.config import settings
from app.core.errors import AppError
from app.schemas.agent import AgentStep, AnalyzeRepoResponse, CoreFileSummary, ToolCallLog
from app.schemas.metrics import CoreFileSelectionMetrics, MockAnalysisMetrics, RepoOperationMetrics, RepoScanMetrics
from app.schemas.repo import RepoParseResponse
from app.services.agent_step_service import AgentStepRecorder
from app.services.analysis_job_service import AnalysisJobService
from app.services.doc_storage_service import create_markdown_docs_dir, save_markdown_document_to_dir, save_markdown_documents
from app.services.file_selector_service import select_core_files_with_metrics
from app.services.file_tree_service import build_file_tree, read_basic_files, scan_repo_metrics
from app.services.github_service import clone_repository
from app.services.llm_call_service import LLMCallService
from app.services.llm_service import DEFAULT_PROVIDER, generate_markdown_documents, has_llm_credentials
from app.services.metrics_service import build_context_quality_report, build_mock_analysis_metrics, record_repo_operation_metrics
from app.mcp.client import StdioMcpClient
from app.mcp.config import get_enabled_server, load_mcp_config
from app.services.repo_parser import parse_github_repo_url
from app.services.result_evaluation_service import evaluate_generated_documents
from app.services.github_mcp_context_service import GITHUB_MCP_ALLOWED_TOOLS, build_github_mcp_context
from app.services.history_service import add_history_record
from app.services.mcp_tool_service import McpToolService
from app.services.tool_log_service import record_tool_call

T = TypeVar("T")

logger = logging.getLogger(__name__)


def run_codebase_analysis_workflow(repo_url: str) -> AnalyzeRepoResponse:
    return _run_codebase_analysis_workflow(repo_url=repo_url)


def require_llm_configuration() -> None:
    _require_llm_api_key()


def _run_codebase_analysis_workflow(*, repo_url: str) -> AnalyzeRepoResponse:
    analysis_started_at = datetime.now(UTC)
    analysis_started = perf_counter()
    steps: list[AgentStep] = []
    tool_logs: list[ToolCallLog] = []
    step_recorder = AgentStepRecorder(steps)
    parsed_repo: RepoParseResponse | None = None
    core_files: list[CoreFileSummary] = []
    repo_scan_metrics = RepoScanMetrics()
    logger.info("[workflow] started | repo_url=%s | mode=real", repo_url)

    try:
        api_key = _require_llm_api_key()
        parsed_repo = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="parse_repo_url",
        title="Parse GitHub URL",
        description="Run workflow stage",
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
        title="Clone repository",
        description="Run workflow stage",
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
        title="Build file tree",
        description="Run workflow stage",
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
        output_summary=lambda result: f"Returned {len(result)} top-level nodes",
        output_payload=lambda result: {"top_level_nodes": len(result)},
        )

        basic_files = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="read_basic_files",
        title="Read basic files",
        description="Run workflow stage",
        tool_name="read_basic_files",
        input_summary=f"max_bytes={settings.max_basic_file_bytes}",
        input_payload={"max_bytes": settings.max_basic_file_bytes},
        action=lambda: read_basic_files(local_path, max_bytes=settings.max_basic_file_bytes),
        output_summary=lambda result: f"Read {len(result)} basic files",
        output_payload=lambda result: {"read_files": [file.path for file in result]},
        related_files=lambda result: [file.path for file in result],
        )

        core_files, selection_metrics = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="select_core_files",
        title="Select core files",
        description="Run workflow stage",
        tool_name="select_core_files",
        input_summary=f"max_files={settings.max_core_files}, max_bytes={settings.max_core_file_bytes}",
        input_payload={"max_files": settings.max_core_files, "max_bytes": settings.max_core_file_bytes},
        action=lambda: select_core_files_with_metrics(
            local_path,
            max_files=settings.max_core_files,
            max_bytes=settings.max_core_file_bytes,
        ),
        output_summary=lambda result: f"Selected {len(result[0])} core files",
        output_payload=lambda result: {
            "candidate_core_files": result[1].candidate_core_files,
            "selected_files": [file.path for file in result[0]],
            "used_for_context": [file.path for file in result[0] if file.used_for_context],
        },
        related_files=lambda result: [file.path for file in result[0]],
        )
        context_quality_report = build_context_quality_report(
            selection_metrics=selection_metrics,
            core_files=core_files,
        )

        analysis_context = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="build_analysis_context",
        title="Build analysis context",
        description="Run workflow stage",
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
        output_summary=lambda result: f"Context has {len(result)} characters",
        output_payload=lambda result: {
            "context_chars": len(result),
            "used_for_context": [file.path for file in core_files if file.used_for_context],
        },
        related_files=lambda _: [file.path for file in core_files if file.used_for_context],
        )

        github_mcp_context = _fetch_optional_github_mcp_context(
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            parsed_repo=parsed_repo,
        )
        if github_mcp_context:
            analysis_context = f"{analysis_context}\n\n{github_mcp_context}"

        recorder = LLMCallService(provider=_llm_provider(), model=_llm_model())
        documents = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="generate_real_ai_documents",
        title="Generate Markdown with LLM",
        description="Run workflow stage",
        tool_name="llm_service.generate_markdown_documents",
        input_summary=f"provider={_llm_provider()}, model={_llm_model()}, docs={len(REAL_DOCUMENT_PROMPTS)}",
        input_payload={"provider": _llm_provider(), "model": _llm_model(), "base_url": _llm_base_url(), "document_count": len(REAL_DOCUMENT_PROMPTS)},
        action=lambda: generate_markdown_documents(
            document_prompts=REAL_DOCUMENT_PROMPTS,
            context=analysis_context,
            api_key=api_key,
            model=_llm_model(),
            base_url=_llm_base_url(),
            recorder=recorder,
        ),
        output_summary=lambda result: f"Generated {len(result)} Markdown documents",
        output_payload=lambda result: {"documents": [filename for _, filename, _ in result]},
        related_files=lambda _: [file.path for file in core_files],
        )
        llm_call_records = recorder.records

        saved_documents, docs_dir = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="save_markdown_docs",
        title="Save Markdown documents",
        description="Run workflow stage",
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
        result_evaluation = _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="evaluate_generated_documents",
        title="Evaluate generated documents",
        description="Run deterministic output checks",
        tool_name="evaluate_generated_documents",
        input_summary=f"documents={len(saved_documents)}, context_files={len(core_files)}",
        input_payload={
            "document_count": len(saved_documents),
            "context_file_count": len([file for file in core_files if file.used_for_context]),
        },
        action=lambda: evaluate_generated_documents(documents=saved_documents, core_files=core_files),
        output_summary=lambda result: f"Quality scores: citations={result.textcitation_score}, coverage={result.coverage_score}",
        output_payload=lambda result: {
            "textcitation_score": result.textcitation_score,
            "coverage_score": result.coverage_score,
            "hallucination_risk": result.hallucination_risk,
            "usefulness_score": result.usefulness_score,
            "issue_count": len(result.issues),
        },
        related_files=lambda _: [file.path for file in core_files if file.used_for_context],
        )
        analysis_duration_ms = int((perf_counter() - analysis_started) * 1000)
        metrics = build_mock_analysis_metrics(
        selection_metrics=selection_metrics,
        core_files=core_files,
        documents=saved_documents,
        analysis_duration_ms=analysis_duration_ms,
        used_mock_ai=False,
        provider=_llm_provider(),
        model=_llm_model(),
        prompt_template_count=len(REAL_DOCUMENT_PROMPTS),
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
            mock_mode=False,
            metrics=metrics,
        )
        logger.info(
            "[workflow] completed | mode=real | duration_ms=%d | docs=%d",
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
            context_quality_report=context_quality_report,
            agent_steps=steps,
            tool_logs=tool_logs,
            documents=saved_documents,
            result_evaluation=result_evaluation,
            docs_dir=docs_dir,
            metrics=metrics,
            mock_mode=False,
        )
    except AppError as exc:
        logger.error(
            "[workflow] failed | repo_url=%s | mode=real | code=%s | message=%s",
            repo_url,
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
            mock_mode=False,
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
    assert_tool_allowed(tool_name)
    step = step_recorder.start(
        key=key,
        title=title,
        description=description,
        metadata={"tool_name": tool_name, "input": input_payload},
    )
    logger.info("[stage] started: %s", title)
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
            message="Codebase analysis workflow failed",
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
    logger.info("[stage] completed: %s | duration_ms=%d", title, duration_ms)
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
        "[stage] failed: %s | code=%s | message=%s | duration_ms=%d",
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
        output_summary="Failed",
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
    logger.info("[stage] skipped: %s | reason=%s", title, reason)
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
        output_summary="Skipped",
        input_payload=input_payload,
        output_payload={"reason": reason},
        duration_ms=0,
        error_message=reason,
    )


def _fetch_optional_github_mcp_context(
    *,
    step_recorder: AgentStepRecorder,
    tool_logs: list[ToolCallLog],
    parsed_repo: RepoParseResponse,
) -> str:
    service = _github_mcp_service()
    input_payload = {"owner": parsed_repo.owner, "repo": parsed_repo.repo}
    if service is None:
        _record_skipped_tool(
            step_recorder,
            tool_logs,
            key="fetch_github_mcp_context",
            title="Fetch GitHub MCP context",
            description="Fetch read-only GitHub collaboration context through MCP",
            tool_name="fetch_github_mcp_context",
            reason="GitHub MCP server is not configured",
            input_payload=input_payload,
        )
        return ""

    return _run_stage(
        step_recorder=step_recorder,
        tool_logs=tool_logs,
        key="fetch_github_mcp_context",
        title="Fetch GitHub MCP context",
        description="Fetch read-only GitHub collaboration context through MCP",
        tool_name="fetch_github_mcp_context",
        input_summary=f"{parsed_repo.owner}/{parsed_repo.repo}",
        input_payload=input_payload,
        action=lambda: build_github_mcp_context(parsed_repo=parsed_repo, tool_logs=tool_logs, service=service),
        output_summary=lambda result: f"GitHub MCP context has {len(result)} characters",
        output_payload=lambda result: {"context_chars": len(result), "enabled": True},
    )


def _github_mcp_service() -> McpToolService | None:
    config_file = getattr(settings, "mcp_config_file", None)
    config = load_mcp_config(
        config_file,
        env_values={"GITHUB_PERSONAL_ACCESS_TOKEN": getattr(settings, "github_personal_access_token", None)},
    )
    server = get_enabled_server(config, "github")
    if server is None:
        return None
    if getattr(settings, "mcp_readonly", True) and not server.readonly:
        return None
    allowed_tools = set(server.allowed_tools) & GITHUB_MCP_ALLOWED_TOOLS
    if not allowed_tools:
        return None
    return McpToolService(
        client=StdioMcpClient([server]),
        server_name=server.name,
        allowed_tools=allowed_tools,
    )


def _llm_provider() -> str:
    return getattr(settings, "llm_provider", None) or DEFAULT_PROVIDER


def _llm_api_key() -> str | None:
    return getattr(settings, "llm_api_key", None) or getattr(settings, "openai_api_key", None)


def _require_llm_api_key() -> str:
    api_key = _llm_api_key()
    if not has_llm_credentials(api_key):
        raise AppError(
            status_code=400,
            code="LLM_API_KEY_MISSING",
            message="未配置 LLM API Key，无法调用真实 AI",
        )
    return api_key.strip()


def _llm_model() -> str:
    return getattr(settings, "llm_model", None) or getattr(settings, "openai_model", None) or "deepseek-v4-flash"


def _llm_base_url() -> str | None:
    return getattr(settings, "llm_base_url", None)


def _record_analysis_metrics(
    *,
    repo_url: str,
    owner: str,
    repo: str,
    started_at: datetime,
    metrics: MockAnalysisMetrics,
) -> None:
    record_repo_operation_metrics(
        RepoOperationMetrics(
            operation="agent_analyze",
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
    metrics: MockAnalysisMetrics | None = None,
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
        metrics=metrics,
    )


def run_codebase_analysis_job(
    *,
    job_id: str,
    repo_url: str,
    job_service: AnalysisJobService,
) -> None:
    analysis_started_at = datetime.now(UTC)
    analysis_started = perf_counter()
    steps: list[AgentStep] = []
    tool_logs: list[ToolCallLog] = []
    step_recorder = AgentStepRecorder(steps)
    parsed_repo: RepoParseResponse | None = None
    core_files: list[CoreFileSummary] = []
    repo_scan_metrics = RepoScanMetrics()
    saved_documents = []
    docs_dir = ""

    try:
        api_key = _require_llm_api_key()
        job_service.update_status(job_id, "running", mock_mode=False)
        job_service.append_event(job_id, "job_started", {"repo_url": repo_url, "mock_mode": False})

        parsed_repo = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="parse_repo_url",
            title="Parse GitHub URL",
            description="Run workflow stage",
            tool_name="parse_github_repo_url",
            input_summary=repo_url,
            input_payload={"repo_url": repo_url},
            action=lambda: parse_github_repo_url(repo_url),
            output_summary=lambda result: f"{result.owner}/{result.repo}",
            output_payload=lambda result: {"owner": result.owner, "repo": result.repo, "repo_url": result.repo_url},
        )
        job_service.update_status(job_id, "running", owner=parsed_repo.owner, repo=parsed_repo.repo, mock_mode=False)

        local_path = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="clone_repository",
            title="Clone repository",
            description="Run workflow stage",
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
            title="Build file tree",
            description="Run workflow stage",
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
            output_summary=lambda result: f"Returned {len(result)} top-level nodes",
            output_payload=lambda result: {"top_level_nodes": len(result)},
        )
        job_service.put_artifact(job_id, "file_tree", [node.model_dump() for node in file_tree])

        basic_files = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="read_basic_files",
            title="Read basic files",
            description="Run workflow stage",
            tool_name="read_basic_files",
            input_summary=f"max_bytes={settings.max_basic_file_bytes}",
            input_payload={"max_bytes": settings.max_basic_file_bytes},
            action=lambda: read_basic_files(local_path, max_bytes=settings.max_basic_file_bytes),
            output_summary=lambda result: f"Read {len(result)} basic files",
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
            title="Select core files",
            description="Run workflow stage",
            tool_name="select_core_files",
            input_summary=f"max_files={settings.max_core_files}, max_bytes={settings.max_core_file_bytes}",
            input_payload={"max_files": settings.max_core_files, "max_bytes": settings.max_core_file_bytes},
            action=lambda: select_core_files_with_metrics(
                local_path,
                max_files=settings.max_core_files,
                max_bytes=settings.max_core_file_bytes,
            ),
            output_summary=lambda result: f"Selected {len(result[0])} core files",
            output_payload=lambda result: {
                "candidate_core_files": result[1].candidate_core_files,
                "selected_files": [file.path for file in result[0]],
                "used_for_context": [file.path for file in result[0] if file.used_for_context],
            },
            related_files=lambda result: [file.path for file in result[0]],
        )
        context_quality_report = build_context_quality_report(
            selection_metrics=selection_metrics,
            core_files=core_files,
        )
        job_service.put_artifact(job_id, "core_files", [file.model_dump() for file in core_files])
        job_service.append_event(
            job_id,
            "stage_completed",
            {
                "key": "repo_loaded",
                "title": "Repository loaded",
                "file_tree": [node.model_dump() for node in file_tree],
                "basic_files": [file.model_dump() for file in basic_files],
                "core_files": [file.model_dump() for file in core_files],
                "context_quality_report": context_quality_report.model_dump(),
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
            used_mock_ai=False,
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
            title="Build analysis context",
            description="Run workflow stage",
            tool_name="build_analysis_context",
            input_summary=f"basic_files={len(basic_files)}, core_files={len(core_files)}",
            input_payload={"basic_files": [file.path for file in basic_files], "core_files": [file.path for file in core_files]},
            action=lambda: build_analysis_context(parsed_repo=parsed_repo, basic_files=basic_files, core_files=core_files),
            output_summary=lambda result: f"Context has {len(result)} characters",
            output_payload=lambda result: {"context_chars": len(result), "used_for_context": [file.path for file in core_files if file.used_for_context]},
            related_files=lambda _: [file.path for file in core_files if file.used_for_context],
        )

        github_mcp_context = _fetch_optional_github_mcp_context(
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            parsed_repo=parsed_repo,
        )
        if github_mcp_context:
            analysis_context = f"{analysis_context}\n\n{github_mcp_context}"

        docs_path, docs_dir = create_markdown_docs_dir(owner=parsed_repo.owner, repo=parsed_repo.repo, docs_root=settings.generated_docs_path)
        job_service.update_status(job_id, "running", docs_dir=docs_dir, core_files_count=len(core_files), mock_mode=False)
        llm_call_records: list = []
        recorder = LLMCallService(provider=_llm_provider(), model=_llm_model())

        for prompt in REAL_DOCUMENT_PROMPTS:
            _raise_if_cancelled(job_id, job_service)
            generated = generate_markdown_documents(
                document_prompts=[prompt],
                context=analysis_context,
                api_key=api_key,
                model=_llm_model(),
                base_url=_llm_base_url(),
                recorder=recorder,
            )
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
                used_mock_ai=False,
                llm_call_records=recorder.records,
                steps=steps,
                tool_logs=tool_logs,
            )
        llm_call_records = recorder.records

        result_evaluation = _run_job_stage(
            job_id=job_id,
            job_service=job_service,
            step_recorder=step_recorder,
            tool_logs=tool_logs,
            key="evaluate_generated_documents",
            title="Evaluate generated documents",
            description="Run deterministic output checks",
            tool_name="evaluate_generated_documents",
            input_summary=f"documents={len(saved_documents)}, context_files={len(core_files)}",
            input_payload={
                "document_count": len(saved_documents),
                "context_file_count": len([file for file in core_files if file.used_for_context]),
            },
            action=lambda: evaluate_generated_documents(documents=saved_documents, core_files=core_files),
            output_summary=lambda result: f"Quality scores: citations={result.textcitation_score}, coverage={result.coverage_score}",
            output_payload=lambda result: {
                "textcitation_score": result.textcitation_score,
                "coverage_score": result.coverage_score,
                "hallucination_risk": result.hallucination_risk,
                "usefulness_score": result.usefulness_score,
                "issue_count": len(result.issues),
            },
            related_files=lambda _: [file.path for file in core_files if file.used_for_context],
        )
        analysis_duration_ms = int((perf_counter() - analysis_started) * 1000)
        metrics = build_mock_analysis_metrics(
            selection_metrics=selection_metrics,
            core_files=core_files,
            documents=saved_documents,
            analysis_duration_ms=analysis_duration_ms,
            used_mock_ai=False,
            provider=_llm_provider(),
            model=_llm_model(),
            prompt_template_count=len(REAL_DOCUMENT_PROMPTS),
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
        )
        response = AnalyzeRepoResponse(
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            repo_url=parsed_repo.repo_url,
            file_tree=file_tree,
            basic_files=basic_files,
            core_files=core_files,
            context_quality_report=context_quality_report,
            agent_steps=steps,
            tool_logs=tool_logs,
            documents=saved_documents,
            result_evaluation=result_evaluation,
            docs_dir=docs_dir,
            metrics=metrics,
            mock_mode=False,
        )
        job_service.put_artifact(job_id, "result", response.model_dump())
        job_service.update_status(job_id, "success", docs_dir=docs_dir, core_files_count=len(core_files), metrics=metrics, mock_mode=False)
        job_service.persist_run_details(
            job_id,
            agent_steps=steps,
            tool_logs=tool_logs,
            llm_call_records=llm_call_records,
        )
        job_service.append_event(job_id, "metrics_updated", {"phase": "completed", "metrics": metrics.model_dump()})
        job_service.append_event(job_id, "job_completed", {"result": response.model_dump(), "metrics": metrics.model_dump(), "docs_dir": docs_dir})
    except _AnalysisJobCancelled:
        job_service.update_status(job_id, "cancelled", docs_dir=docs_dir, core_files_count=len(core_files), error_message="Analysis stopped by user", mock_mode=False)
        job_service.persist_run_details(
            job_id,
            agent_steps=steps,
            tool_logs=tool_logs,
            llm_call_records=[],
        )
        job_service.append_event(job_id, "job_cancelled", {"message": "Analysis stopped by user", "documents": [document.model_dump() for document in saved_documents]})
    except AppError as exc:
        job_service.update_status(job_id, "failed", docs_dir=docs_dir, core_files_count=len(core_files), error_message=exc.detail or exc.message, mock_mode=False)
        job_service.persist_run_details(
            job_id,
            agent_steps=steps,
            tool_logs=tool_logs,
            llm_call_records=[],
        )
        job_service.append_event(job_id, "job_failed", {"code": exc.code, "message": exc.message, "detail": exc.detail, "documents": [document.model_dump() for document in saved_documents]})
    except Exception as exc:
        logger.exception("[analyze-job] unexpected failure | job_id=%s | repo_url=%s", job_id, repo_url)
        message = str(exc) or "Unexpected analysis failure"
        job_service.update_status(
            job_id,
            "failed",
            docs_dir=docs_dir,
            core_files_count=len(core_files),
            error_message=message,
            mock_mode=False,
        )
        job_service.persist_run_details(
            job_id,
            agent_steps=steps,
            tool_logs=tool_logs,
            llm_call_records=[],
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
    used_mock_ai: bool,
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
        used_mock_ai=used_mock_ai,
        provider=_llm_provider(),
        model=_llm_model(),
        prompt_template_count=len(REAL_DOCUMENT_PROMPTS),
        llm_call_records=llm_call_records,
        agent_steps=steps,
        tool_logs=tool_logs,
    )
    job_service.append_event(job_id, "metrics_updated", {"phase": phase, "metrics": metrics.model_dump()})
