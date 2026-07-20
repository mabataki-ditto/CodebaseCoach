from pathlib import Path
from collections.abc import Callable
from typing import Any, cast

from app.agent_graph.context import AnalysisRuntimeContext
from app.agent_graph.graph_builder import build_analysis_graph
from app.agent_graph.state import AnalysisState
from app.core.config import get_settings
from app.core.errors import AppError
from app.services.graph_run_service import GraphRunService
from app.services.mcp_tool_service import McpToolService
from app.services.repo_parser import parse_github_repo_url


def run_analysis_graph(
    repo_url: str,
    *,
    job_id: str | None = None,
    mcp_service: McpToolService | None = None,
    include_document_generation: bool = False,
    include_quality_loop: bool = False,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    llm_provider: str | None = None,
    graph_run_service: GraphRunService | None = None,
    thread_id: str | None = None,
    resume: bool = False,
    on_graph_event: Callable[[dict[str, Any]], None] | None = None,
    on_state_update: Callable[[AnalysisState], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    selective_quality_retry: bool = False,
    recovery_initial_state: AnalysisState | None = None,
) -> AnalysisState:
    """Synchronously run or explicitly resume the opt-in analysis graph."""
    graph_thread_id = thread_id or job_id
    if graph_run_service is not None and not graph_thread_id:
        raise AppError(
            status_code=400,
            code="GRAPH_THREAD_ID_MISSING",
            message="LangGraph persistent runs require a thread id or job id",
        )
    if resume and graph_run_service is None:
        raise AppError(
            status_code=400,
            code="GRAPH_CHECKPOINTER_REQUIRED",
            message="LangGraph recovery requires a graph run service",
        )

    initial_state: AnalysisState = {
        **(recovery_initial_state or {}),
        "repo_url": repo_url,
        "agent_steps": (recovery_initial_state or {}).get("agent_steps", []),
        "tool_logs": (recovery_initial_state or {}).get("tool_logs", []),
    }
    if job_id is not None:
        initial_state["job_id"] = job_id
    if include_quality_loop:
        initial_state["quality_retry_count"] = 0

    settings = get_settings()
    graph = build_analysis_graph(
        include_document_generation=include_document_generation,
        include_quality_loop=include_quality_loop,
        checkpointer=graph_run_service.checkpointer if graph_run_service else None,
        selective_quality_retry=selective_quality_retry,
    )
    runtime_context: AnalysisRuntimeContext = {
        "mcp_service": mcp_service,
        "llm_api_key": llm_api_key,
        "llm_model": llm_model or settings.llm_model,
        "llm_base_url": llm_base_url or settings.llm_base_url,
        "llm_provider": llm_provider or settings.llm_provider,
        "cancel_check": cancel_check,
    }
    config: dict = {"max_concurrency": settings.llm_max_workers}
    graph_input: AnalysisState | None = initial_state
    if graph_run_service is not None:
        assert graph_thread_id is not None
        config = graph_run_service.thread_config(
            graph_thread_id,
            max_concurrency=settings.llm_max_workers,
        )
        checkpoint_exists = graph_run_service.has_checkpoint(graph_thread_id)
        if resume:
            if not checkpoint_exists:
                raise AppError(
                    status_code=404,
                    code="GRAPH_CHECKPOINT_NOT_FOUND",
                    message="LangGraph checkpoint was not found",
                    detail=graph_thread_id,
                )
            checkpoint_snapshot = graph.get_state(config)
            checkpoint_state = cast(AnalysisState, checkpoint_snapshot.values)
            _validate_resume_state(checkpoint_state, repo_url=repo_url)
            graph_input = None
        elif checkpoint_exists:
            raise AppError(
                status_code=409,
                code="GRAPH_THREAD_EXISTS",
                message="LangGraph thread already has checkpoint state",
                detail=graph_thread_id,
            )

    if on_graph_event is None:
        return cast(
            AnalysisState,
            graph.invoke(
                graph_input,
                context=runtime_context,
                config=config,
            ),
        )

    if cancel_check is not None:
        cancel_check()
    final_state: AnalysisState = {}
    for part in graph.stream(
        graph_input,
        context=runtime_context,
        config=config,
        stream_mode=["custom", "values"],
        version="v2",
    ):
        if part["type"] == "custom" and isinstance(part["data"], dict):
            on_graph_event(part["data"])
        elif part["type"] == "values":
            final_state = cast(AnalysisState, part["data"])
            if on_state_update is not None:
                on_state_update(final_state)
        if cancel_check is not None:
            cancel_check()
    if not final_state and graph_run_service is not None:
        final_state = cast(AnalysisState, graph.get_state(config).values)
        if on_state_update is not None:
            on_state_update(final_state)
    return final_state


def _validate_resume_state(state: AnalysisState, *, repo_url: str) -> None:
    checkpoint_repo_url = state.get("repo_url")
    checkpoint_parsed_repo = state.get("parsed_repo")
    requested_repo_url = parse_github_repo_url(repo_url).repo_url
    if checkpoint_parsed_repo is not None:
        persisted_repo_url = checkpoint_parsed_repo.repo_url
    elif checkpoint_repo_url:
        persisted_repo_url = parse_github_repo_url(checkpoint_repo_url).repo_url
    else:
        persisted_repo_url = requested_repo_url
    if persisted_repo_url != requested_repo_url:
        raise AppError(
            status_code=409,
            code="GRAPH_REPO_MISMATCH",
            message="LangGraph checkpoint belongs to another repository",
            detail=persisted_repo_url,
        )
    local_path = state.get("local_path")
    if local_path and not Path(local_path).is_dir():
        raise AppError(
            status_code=409,
            code="GRAPH_LOCAL_PATH_MISSING",
            message="The cloned repository required by this checkpoint is unavailable",
            detail=local_path,
        )
