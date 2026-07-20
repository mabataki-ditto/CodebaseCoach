import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from app.agent.prompts import REAL_DOCUMENT_PROMPTS
from app.agent.workflow import (
    _github_mcp_service,
    _record_history,
    _require_llm_api_key,
    run_codebase_analysis_job,
    run_codebase_analysis_workflow,
)
from app.agent_graph.runner import run_analysis_graph
from app.agent_graph.stage_adapter import GraphStageAdapter
from app.agent_graph.state import AnalysisState
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.agent import AnalyzeRepoResponse, GeneratedDocument
from app.schemas.analysis_job import AnalysisJobResumeResponse, AnalysisJobResumeStatusResponse
from app.schemas.metrics import MockAnalysisMetrics, RepoScanMetrics
from app.services.analysis_job_service import AnalysisJobService
from app.services.doc_storage_service import save_markdown_documents
from app.services.graph_run_service import GraphRunService
from app.services.langgraph_event_adapter import LangGraphEventAdapter
from app.services.metrics_service import build_mock_analysis_metrics
from app.services.mcp_tool_service import McpToolService


logger = logging.getLogger(__name__)


class AnalysisJobCancelled(Exception):
    """Internal cooperative-cancellation signal for a LangGraph job run."""


def langgraph_thread_id(job_id: str) -> str:
    return f"analysis:{job_id}"


class AnalysisExecutionService:
    """Select and execute one analysis engine behind the existing API contract."""

    def __init__(
        self,
        *,
        settings_provider: Callable[[], Settings] = get_settings,
        legacy_sync_runner: Callable[[str], Any] = run_codebase_analysis_workflow,
        legacy_job_runner: Callable[..., None] = run_codebase_analysis_job,
        graph_runner: Callable[..., AnalysisState] = run_analysis_graph,
        mcp_service_factory: Callable[[], McpToolService | None] = _github_mcp_service,
        api_key_provider: Callable[[], str] = _require_llm_api_key,
        graph_run_service_factory: Callable[[Any], GraphRunService] = GraphRunService,
    ) -> None:
        self._settings_provider = settings_provider
        self._legacy_sync_runner = legacy_sync_runner
        self._legacy_job_runner = legacy_job_runner
        self._graph_runner = graph_runner
        self._mcp_service_factory = mcp_service_factory
        self._api_key_provider = api_key_provider
        self._graph_run_service_factory = graph_run_service_factory

    def get_resume_status(
        self,
        job_id: str,
        job_service: AnalysisJobService,
    ) -> AnalysisJobResumeStatusResponse:
        job = job_service.get_job(job_id)
        metadata = job_service.get_artifact_payload(job_id, "execution_metadata")
        engine = metadata.get("engine") if isinstance(metadata, dict) else None

        reason: str | None = None
        if job.status != "failed":
            reason = f"任务状态 {job.status} 不允许恢复"
        elif engine != "langgraph":
            reason = "任务不是由 LangGraph 执行，无法恢复"
        elif self._settings_provider().analysis_engine != "langgraph":
            reason = "当前服务未启用 LangGraph"

        recovery_mode = None
        if reason is None:
            settings = self._settings_provider()
            thread_id = langgraph_thread_id(job_id)
            with self._graph_run_service_factory(settings.graph_checkpoint_path) as graph_runs:
                if not graph_runs.has_checkpoint(thread_id):
                    reason = "任务 Checkpoint 不存在"
                else:
                    state = graph_runs.get_checkpoint_state(thread_id)
                    local_path = state.get("local_path")
                    if isinstance(local_path, str) and Path(local_path).is_dir():
                        recovery_mode = "checkpoint"
                    elif state.get("repository_commit_sha") or state.get("recovery_source_commit_sha"):
                        recovery_mode = "rebuild_repository"
                    else:
                        recovery_mode = "full_restart"

        return AnalysisJobResumeStatusResponse(
            job_id=job.id,
            can_resume=reason is None,
            job_status=job.status,
            engine=engine,
            recovery_mode=recovery_mode,
            reason=reason,
        )

    def resume_job(
        self,
        job_id: str,
        job_service: AnalysisJobService,
    ) -> AnalysisJobResumeResponse:
        status = self.get_resume_status(job_id, job_service)
        if not status.can_resume or status.recovery_mode is None:
            raise AppError(
                status_code=409,
                code="ANALYSIS_JOB_NOT_RESUMABLE",
                message="当前任务无法恢复",
                detail=status.reason,
            )
        job = job_service.try_prepare_resume(job_id)
        metadata = job_service.get_artifact_payload(job_id, "execution_metadata")
        job_service.put_artifact(
            job_id,
            "execution_metadata",
            {
                **(metadata if isinstance(metadata, dict) else {}),
                "resume_requested": True,
                "recovery_mode": status.recovery_mode,
            },
        )
        return AnalysisJobResumeResponse(
            job_id=job.id,
            status=job.status,
            resumed=True,
            recovery_mode=status.recovery_mode,
        )

    def run_sync(self, repo_url: str) -> AnalyzeRepoResponse:
        if self._settings_provider().analysis_engine == "legacy":
            return self._legacy_sync_runner(repo_url)
        return self._run_langgraph_sync(repo_url)

    def run_job(
        self,
        *,
        job_id: str,
        repo_url: str,
        job_service: AnalysisJobService,
    ) -> None:
        if self._settings_provider().analysis_engine == "legacy":
            self._legacy_job_runner(
                job_id=job_id,
                repo_url=repo_url,
                job_service=job_service,
            )
            return
        self._run_langgraph_job(job_id=job_id, repo_url=repo_url, job_service=job_service)

    @staticmethod
    def raise_if_cancelled(job_id: str, job_service: AnalysisJobService) -> None:
        if job_service.is_cancel_requested(job_id):
            raise AnalysisJobCancelled()

    def cleanup_checkpoint(self, job_id: str) -> None:
        settings = self._settings_provider()
        with GraphRunService(settings.graph_checkpoint_path) as graph_runs:
            graph_runs.delete_thread(langgraph_thread_id(job_id))

    def _run_langgraph_sync(self, repo_url: str) -> AnalyzeRepoResponse:
        settings = self._settings_provider()
        started_at = datetime.now(UTC)
        started = perf_counter()
        try:
            state = self._graph_runner(
                repo_url,
                include_quality_loop=True,
                selective_quality_retry=True,
                mcp_service=self._mcp_service_factory(),
                llm_api_key=self._api_key_provider(),
                llm_model=settings.llm_model,
                llm_base_url=settings.llm_base_url,
                llm_provider=settings.llm_provider,
            )
            response = self._finalize_graph_state(state, started=started, settings=settings)
            _record_history(
                repo_url=response.repo_url,
                owner=response.owner,
                repo=response.repo,
                status="success",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                docs_dir=response.docs_dir,
                core_files_count=len(response.core_files),
                error_message=None,
                mock_mode=False,
                metrics=response.metrics,
            )
            return response
        except AppError as error:
            _record_history(
                repo_url=repo_url,
                owner="",
                repo="",
                status="failed",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                docs_dir="",
                core_files_count=0,
                error_message=error.detail or error.message,
                mock_mode=False,
            )
            raise

    def _run_langgraph_job(
        self,
        *,
        job_id: str,
        repo_url: str,
        job_service: AnalysisJobService,
    ) -> None:
        settings = self._settings_provider()
        started = perf_counter()
        thread_id = langgraph_thread_id(job_id)
        adapter = LangGraphEventAdapter(job_id=job_id, job_service=job_service)
        latest_state: AnalysisState = {}
        completed_documents: dict[int, tuple[str, str, str]] = {}
        persisted_artifacts = self._existing_artifact_types(job_id, job_service)
        repo_loaded_emitted = self._has_repo_loaded_event(job_id, job_service)
        response: AnalyzeRepoResponse | None = None
        execution_metadata = job_service.get_artifact_payload(job_id, "execution_metadata")
        if not isinstance(execution_metadata, dict):
            execution_metadata = {}
        repository_refresh_sha = execution_metadata.get("repository_context_commit_sha")

        def cancel_check() -> None:
            self.raise_if_cancelled(job_id, job_service)

        def handle_graph_event(event: dict[str, Any]) -> None:
            if event.get("type") == "document_ready":
                payload = event.get("payload", {})
                if isinstance(payload, dict) and isinstance(payload.get("index"), int):
                    completed_documents[payload["index"]] = (
                        str(payload.get("title", "")),
                        str(payload.get("filename", "")),
                        str(payload.get("content", "")),
                    )
                return
            adapter.handle_custom_event(event)

        def observe_state(state: AnalysisState) -> None:
            nonlocal latest_state, repo_loaded_emitted, execution_metadata, repository_refresh_sha
            latest_state = state
            parsed_repo = state.get("parsed_repo")
            if parsed_repo is not None:
                job_service.update_status(
                    job_id,
                    "running",
                    owner=parsed_repo.owner,
                    repo=parsed_repo.repo,
                    mock_mode=False,
                )
            commit_sha = state.get("repository_commit_sha")
            recovery_mode = state.get("recovery_mode")
            if (
                recovery_mode == "full_restart"
                and execution_metadata.get("recovery_mode") != "full_restart"
            ):
                adapter.append(
                    "stage_started",
                    {
                        "key": "repository_recovery_full_restart",
                        "title": "仓库版本已变化，重新生成全部文档",
                        "description": "Discard recovered documents from a different commit",
                    },
                )
            if (
                recovery_mode == "full_restart"
                and commit_sha
                and repository_refresh_sha != commit_sha
            ):
                persisted_artifacts.difference_update({"file_tree", "basic_files", "core_files"})
                repo_loaded_emitted = False
                repository_refresh_sha = commit_sha
            if (
                (commit_sha is not None and commit_sha != execution_metadata.get("repository_commit_sha"))
                or (
                    recovery_mode is not None
                    and recovery_mode != execution_metadata.get("recovery_mode")
                )
            ):
                execution_metadata = {**execution_metadata}
                if commit_sha is not None:
                    execution_metadata["repository_commit_sha"] = commit_sha
                if recovery_mode is not None:
                    execution_metadata["recovery_mode"] = recovery_mode
                job_service.put_artifact(job_id, "execution_metadata", execution_metadata)
            for artifact_type in ("file_tree", "basic_files", "core_files"):
                values = state.get(artifact_type)
                if values is not None and artifact_type not in persisted_artifacts:
                    job_service.put_artifact(
                        job_id,
                        artifact_type,
                        [value.model_dump() for value in values],
                    )
                    persisted_artifacts.add(artifact_type)
            if state.get("context_quality_report") is not None and not repo_loaded_emitted:
                adapter.append(
                    "stage_completed",
                    {
                        "key": "repo_loaded",
                        "title": "Repository loaded",
                        "file_tree": [value.model_dump() for value in state.get("file_tree", [])],
                        "basic_files": [value.model_dump() for value in state.get("basic_files", [])],
                        "core_files": [value.model_dump() for value in state.get("core_files", [])],
                        "context_quality_report": state["context_quality_report"].model_dump(),
                    },
                )
                adapter.append(
                    "metrics_updated",
                    {
                        "phase": "repo_loaded",
                        "metrics": self._build_metrics(
                            state,
                            documents=[],
                            started=started,
                            settings=settings,
                        ).model_dump(),
                    },
                )
                repo_loaded_emitted = True
                execution_metadata = {
                    **execution_metadata,
                    "repository_context_commit_sha": state.get("repository_commit_sha"),
                }
                job_service.put_artifact(job_id, "execution_metadata", execution_metadata)

        try:
            api_key = self._api_key_provider()
            job_service.update_status(job_id, "running", mock_mode=False)
            with self._graph_run_service_factory(settings.graph_checkpoint_path) as graph_runs:
                resume = graph_runs.has_checkpoint(thread_id)
                if execution_metadata.get("resume_requested") and not resume:
                    raise AppError(
                        status_code=404,
                        code="GRAPH_CHECKPOINT_NOT_FOUND",
                        message="LangGraph checkpoint was not found",
                    )
                recovery_mode = "checkpoint" if resume else None
                recovery_initial_state = None
                if resume:
                    job_service.prepare_resume(job_id)
                    checkpoint_state = graph_runs.get_checkpoint_state(thread_id)
                    local_path = checkpoint_state.get("local_path")
                    if not (isinstance(local_path, str) and Path(local_path).is_dir()):
                        recovery_initial_state = self._build_repository_recovery_state(
                            checkpoint_state,
                            repo_url=repo_url,
                            job_id=job_id,
                        )
                        recovery_mode = recovery_initial_state["recovery_mode"]
                        graph_runs.delete_thread(thread_id)
                        resume = False
                previous_attempt = execution_metadata.get("resume_attempt", 0)
                resume_attempt = int(previous_attempt) + 1 if recovery_mode else int(previous_attempt)
                execution_metadata = {
                    **execution_metadata,
                    "engine": "langgraph",
                    "thread_id": thread_id,
                    "resumed": recovery_mode is not None,
                    "recovery_mode": recovery_mode,
                    "resume_attempt": resume_attempt,
                    "resume_requested": False,
                }
                job_service.put_artifact(
                    job_id,
                    "execution_metadata",
                    execution_metadata,
                )
                adapter.append(
                    "job_started",
                    {
                        "repo_url": repo_url,
                        "mock_mode": False,
                        "resumed": recovery_mode is not None,
                        "recovery_mode": recovery_mode,
                    },
                )
                state = self._graph_runner(
                    repo_url,
                    job_id=job_id,
                    graph_run_service=graph_runs,
                    thread_id=thread_id,
                    resume=resume,
                    recovery_initial_state=recovery_initial_state,
                    include_quality_loop=True,
                    selective_quality_retry=True,
                    mcp_service=self._mcp_service_factory(),
                    llm_api_key=api_key,
                    llm_model=settings.llm_model,
                    llm_base_url=settings.llm_base_url,
                    llm_provider=settings.llm_provider,
                    on_graph_event=handle_graph_event,
                    on_state_update=observe_state,
                    cancel_check=cancel_check,
                )
                latest_state = state or latest_state
                cancel_check()
                existing_documents, existing_docs_dir = self._existing_documents(job_id, job_service)
                if recovery_mode == "full_restart":
                    existing_documents, existing_docs_dir = [], ""
                response = self._finalize_graph_state(
                    latest_state,
                    started=started,
                    settings=settings,
                    existing_documents=existing_documents,
                    existing_docs_dir=existing_docs_dir,
                )
                job_service.put_artifact(
                    job_id,
                    "documents",
                    [document.model_dump() for document in response.documents],
                )
                job_service.update_status(
                    job_id,
                    "running",
                    docs_dir=response.docs_dir,
                    core_files_count=len(response.core_files),
                    mock_mode=False,
                )
                emitted_documents = self._emitted_document_filenames(job_id, job_service)
                for index, document in enumerate(response.documents, start=1):
                    if document.filename in emitted_documents:
                        continue
                    adapter.append(
                        "document_generated",
                        {
                            "document": document.model_dump(),
                            "index": index,
                            "total": len(response.documents),
                        },
                    )
                    adapter.append(
                        "metrics_updated",
                        {
                            "phase": "document_generated",
                            "metrics": self._build_metrics(
                                latest_state,
                                documents=response.documents[:index],
                                started=started,
                                settings=settings,
                                agent_steps=response.agent_steps,
                                tool_logs=response.tool_logs,
                            ).model_dump(),
                        },
                    )
                cancel_check()
                job_service.put_artifact(job_id, "result", response.model_dump())
                job_service.persist_run_details(
                    job_id,
                    agent_steps=response.agent_steps,
                    tool_logs=response.tool_logs,
                    llm_call_records=latest_state.get("llm_call_records", []),
                )
                job_service.update_status(
                    job_id,
                    "success",
                    docs_dir=response.docs_dir,
                    core_files_count=len(response.core_files),
                    metrics=response.metrics,
                    mock_mode=False,
                )
                if not self._has_completed_metrics_event(job_id, job_service):
                    adapter.append(
                        "metrics_updated",
                        {"phase": "completed", "metrics": response.metrics.model_dump()},
                    )
                adapter.append(
                    "job_completed",
                    {
                        "result": response.model_dump(),
                        "metrics": response.metrics.model_dump(),
                        "docs_dir": response.docs_dir,
                    },
                )
                self._safe_delete_checkpoint(graph_runs, thread_id)
        except AnalysisJobCancelled:
            self._finish_cancelled_job(
                job_id=job_id,
                job_service=job_service,
                adapter=adapter,
                state=latest_state,
                response=response,
                settings=settings,
                completed_documents=completed_documents,
            )
            try:
                self.cleanup_checkpoint(job_id)
            except Exception:
                logger.exception(
                    "[langgraph-job] checkpoint cleanup failed after cancellation | job_id=%s",
                    job_id,
                )
        except AppError as error:
            self._finish_failed_job(
                job_id=job_id,
                job_service=job_service,
                adapter=adapter,
                state=latest_state,
                error=error,
            )
        except Exception as error:
            logger.exception("[langgraph-job] unexpected failure | job_id=%s", job_id)
            app_error = AppError(
                status_code=500,
                code="ANALYSIS_JOB_FAILED",
                message="Analysis failed",
                detail=str(error) or "Unexpected analysis failure",
            )
            self._finish_failed_job(
                job_id=job_id,
                job_service=job_service,
                adapter=adapter,
                state=latest_state,
                error=app_error,
            )

    def _finalize_graph_state(
        self,
        state: AnalysisState,
        *,
        started: float,
        settings: Settings,
        existing_documents: list[GeneratedDocument] | None = None,
        existing_docs_dir: str = "",
    ) -> AnalyzeRepoResponse:
        parsed_repo = state["parsed_repo"]
        adapter = GraphStageAdapter(state)
        if existing_documents and existing_docs_dir:
            saved_documents = existing_documents
            docs_dir = existing_docs_dir
        else:
            saved_documents, docs_dir = adapter.run(
                key="save_markdown_docs",
                title="Save Markdown documents",
                description="Run workflow stage",
                tool_name="save_markdown_documents",
                input_summary=settings.generated_docs_path.as_posix(),
                input_payload={
                    "docs_root": settings.generated_docs_path.as_posix(),
                    "document_count": len(state["documents"]),
                },
                action=lambda: save_markdown_documents(
                    owner=parsed_repo.owner,
                    repo=parsed_repo.repo,
                    docs_root=settings.generated_docs_path,
                    documents=state["documents"],
                ),
                output_summary=lambda result: result[1],
                output_payload=lambda result: {
                    "docs_dir": result[1],
                    "documents": [document.path for document in result[0]],
                },
            )
        audit = adapter.state_update()
        metrics = self._build_metrics(
            state,
            documents=saved_documents,
            started=started,
            settings=settings,
            agent_steps=audit["agent_steps"],
            tool_logs=audit["tool_logs"],
        )
        return AnalyzeRepoResponse(
            owner=parsed_repo.owner,
            repo=parsed_repo.repo,
            repo_url=parsed_repo.repo_url,
            file_tree=state["file_tree"],
            basic_files=state["basic_files"],
            core_files=state["core_files"],
            context_quality_report=state["context_quality_report"],
            agent_steps=audit["agent_steps"],
            tool_logs=audit["tool_logs"],
            documents=saved_documents,
            result_evaluation=state["result_evaluation"],
            docs_dir=docs_dir,
            metrics=metrics,
            mock_mode=False,
        )

    @staticmethod
    def _build_repository_recovery_state(
        checkpoint_state: AnalysisState,
        *,
        repo_url: str,
        job_id: str,
    ) -> AnalysisState:
        source_sha = checkpoint_state.get("repository_commit_sha") or checkpoint_state.get(
            "recovery_source_commit_sha", ""
        )
        recovery_state: AnalysisState = {
            "job_id": job_id,
            "repo_url": repo_url,
            "agent_steps": [],
            "tool_logs": [],
            "quality_retry_count": 0,
            "recovery_mode": "rebuild_repository" if source_sha else "full_restart",
        }
        if source_sha:
            recovery_state["recovery_source_commit_sha"] = source_sha
            document_results = checkpoint_state.get("document_results")
            if document_results:
                recovery_state["document_results"] = document_results
        return recovery_state

    @staticmethod
    def _build_metrics(
        state: AnalysisState,
        *,
        documents: list[GeneratedDocument],
        started: float,
        settings: Settings,
        agent_steps: list | None = None,
        tool_logs: list | None = None,
    ) -> MockAnalysisMetrics:
        return build_mock_analysis_metrics(
            selection_metrics=state["selection_metrics"],
            repo_scan_metrics=state.get("repo_scan_metrics", RepoScanMetrics()),
            core_files=state["core_files"],
            documents=documents,
            analysis_duration_ms=int((perf_counter() - started) * 1000),
            used_mock_ai=False,
            provider=settings.llm_provider,
            model=settings.llm_model,
            prompt_template_count=len(REAL_DOCUMENT_PROMPTS),
            llm_call_records=state.get("llm_call_records", []),
            agent_steps=agent_steps or state.get("agent_steps", []),
            tool_logs=tool_logs or state.get("tool_logs", []),
        )

    @staticmethod
    def _existing_artifact_types(job_id: str, job_service: AnalysisJobService) -> set[str]:
        return {
            artifact_type
            for artifact_type in ("file_tree", "basic_files", "core_files", "documents", "result")
            if job_service.has_artifact(job_id, artifact_type)
        }

    @staticmethod
    def _existing_documents(
        job_id: str,
        job_service: AnalysisJobService,
    ) -> tuple[list[GeneratedDocument], str]:
        snapshot = job_service.get_snapshot(job_id)
        return snapshot.documents, snapshot.job.docs_dir

    @staticmethod
    def _has_repo_loaded_event(job_id: str, job_service: AnalysisJobService) -> bool:
        return any(
            event.type == "stage_completed" and event.payload.get("key") == "repo_loaded"
            for event in job_service.get_events_after(job_id, 0)
        )

    @staticmethod
    def _emitted_document_filenames(job_id: str, job_service: AnalysisJobService) -> set[str]:
        filenames: set[str] = set()
        for event in job_service.get_events_after(job_id, 0):
            if event.type != "document_generated":
                continue
            document = event.payload.get("document")
            if isinstance(document, dict) and isinstance(document.get("filename"), str):
                filenames.add(document["filename"])
        return filenames

    @staticmethod
    def _has_completed_metrics_event(job_id: str, job_service: AnalysisJobService) -> bool:
        return any(
            event.type == "metrics_updated" and event.payload.get("phase") == "completed"
            for event in job_service.get_events_after(job_id, 0)
        )

    def _finish_cancelled_job(
        self,
        *,
        job_id: str,
        job_service: AnalysisJobService,
        adapter: LangGraphEventAdapter,
        state: AnalysisState,
        response: AnalyzeRepoResponse | None,
        settings: Settings,
        completed_documents: dict[int, tuple[str, str, str]],
    ) -> None:
        snapshot = job_service.get_snapshot(job_id)
        documents = response.documents if response else snapshot.documents
        docs_dir = response.docs_dir if response else snapshot.job.docs_dir
        if not documents and completed_documents:
            try:
                completed_indices = sorted(completed_documents)
                documents, docs_dir = save_markdown_documents(
                    owner=state["parsed_repo"].owner,
                    repo=state["parsed_repo"].repo,
                    docs_root=settings.generated_docs_path,
                    documents=[completed_documents[index] for index in completed_indices],
                )
                job_service.put_artifact(
                    job_id,
                    "documents",
                    [document.model_dump() for document in documents],
                )
                for document_index, document in zip(completed_indices, documents, strict=True):
                    adapter.append(
                        "document_generated",
                        {
                            "document": document.model_dump(),
                            "index": document_index + 1,
                            "total": len(REAL_DOCUMENT_PROMPTS),
                        },
                    )
            except (AppError, KeyError):
                logger.exception(
                    "[langgraph-job] unable to persist completed documents during cancellation | job_id=%s",
                    job_id,
                )
        steps = response.agent_steps if response else state.get("agent_steps", [])
        tool_logs = response.tool_logs if response else state.get("tool_logs", [])
        job_service.update_status(
            job_id,
            "cancelled",
            docs_dir=docs_dir,
            core_files_count=len(state.get("core_files", [])),
            error_message="Analysis stopped by user",
            mock_mode=False,
        )
        job_service.persist_run_details(
            job_id,
            agent_steps=steps,
            tool_logs=tool_logs,
            llm_call_records=state.get("llm_call_records", []),
        )
        adapter.append(
            "job_cancelled",
            {
                "message": "Analysis stopped by user",
                "documents": [document.model_dump() for document in documents],
            },
        )

    @staticmethod
    def _finish_failed_job(
        *,
        job_id: str,
        job_service: AnalysisJobService,
        adapter: LangGraphEventAdapter,
        state: AnalysisState,
        error: AppError,
    ) -> None:
        snapshot = job_service.get_snapshot(job_id)
        steps = error.agent_steps or state.get("agent_steps", [])
        tool_logs = error.tool_logs or state.get("tool_logs", [])
        job_service.update_status(
            job_id,
            "failed",
            docs_dir=snapshot.job.docs_dir,
            core_files_count=len(state.get("core_files", [])),
            error_message=error.detail or error.message,
            mock_mode=False,
        )
        job_service.persist_run_details(
            job_id,
            agent_steps=steps,
            tool_logs=tool_logs,
            llm_call_records=state.get("llm_call_records", []),
        )
        adapter.append(
            "job_failed",
            {
                "code": error.code,
                "message": error.message,
                "detail": error.detail,
                "documents": [document.model_dump() for document in snapshot.documents],
            },
        )

    @staticmethod
    def _safe_delete_checkpoint(graph_runs: GraphRunService, thread_id: str) -> None:
        try:
            graph_runs.delete_thread(thread_id)
        except Exception:
            logger.exception(
                "[langgraph-job] checkpoint cleanup failed after success | thread_id=%s",
                thread_id,
            )


analysis_execution_service = AnalysisExecutionService()
