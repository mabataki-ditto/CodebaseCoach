from datetime import UTC, datetime
from typing import Any

from app.core.errors import AppError
from app.schemas.agent import AnalyzeRepoResponse, CoreFileSummary, GeneratedDocument
from app.schemas.agent import AgentStep, ToolCallLog
from app.schemas.analysis_job import (
    AnalysisArtifact,
    AnalysisEvent,
    AnalysisEventType,
    AnalysisJob,
    AnalysisJobSnapshot,
    AnalysisJobStatus,
)
from app.schemas.repo import BasicFileSummary, FileTreeNode
from app.services.analysis_job_repository import (
    AnalysisArtifactRepository,
    AnalysisEventRepository,
    AnalysisJobRepository,
)
from app.services.llm_call_service import LLMCallRecord


class AnalysisJobService:
    def __init__(
        self,
        *,
        job_repository: AnalysisJobRepository,
        event_repository: AnalysisEventRepository,
        artifact_repository: AnalysisArtifactRepository,
    ) -> None:
        self._jobs = job_repository
        self._events = event_repository
        self._artifacts = artifact_repository

    def create_job(self, repo_url: str) -> AnalysisJob:
        now = _now()
        return self._jobs.create_job(
            AnalysisJob(
                repo_url=repo_url,
                created_at=now,
                updated_at=now,
            )
        )

    def get_job(self, job_id: str) -> AnalysisJob:
        job = self._jobs.get_job(job_id)
        if job is None:
            raise AppError(
                status_code=404,
                code="ANALYSIS_JOB_NOT_FOUND",
                message="分析任务不存在",
                detail=job_id,
            )
        return job

    def update_status(
        self,
        job_id: str,
        status: AnalysisJobStatus,
        *,
        owner: str | None = None,
        repo: str | None = None,
        docs_dir: str | None = None,
        core_files_count: int | None = None,
        error_message: str | None = None,
        metrics: Any | None = None,
        mock_mode: bool | None = None,
    ) -> AnalysisJob:
        job = self.get_job(job_id)
        job.status = status
        job.updated_at = _now()
        if status in {"success", "failed", "cancelled"}:
            job.completed_at = job.updated_at
        if owner is not None:
            job.owner = owner
        if repo is not None:
            job.repo = repo
        if docs_dir is not None:
            job.docs_dir = docs_dir
        if core_files_count is not None:
            job.core_files_count = core_files_count
        if error_message is not None:
            job.error_message = error_message
        if metrics is not None:
            job.metrics = metrics
        if mock_mode is not None:
            job.mock_mode = mock_mode
        return self._jobs.update_job(job)

    def request_cancel(self, job_id: str) -> AnalysisJob:
        job = self.get_job(job_id)
        job.cancel_requested = True
        job.updated_at = _now()
        return self._jobs.update_job(job)

    def prepare_resume(self, job_id: str) -> AnalysisJob:
        job = self.get_job(job_id)
        job.status = "running"
        job.updated_at = _now()
        job.completed_at = None
        job.error_message = None
        return self._jobs.update_job(job)

    def try_prepare_resume(self, job_id: str) -> AnalysisJob:
        job = self._jobs.try_transition_status(
            job_id,
            expected_statuses={"failed"},
            new_status="running",
        )
        if job is None:
            current = self.get_job(job_id)
            raise AppError(
                status_code=409,
                code="ANALYSIS_JOB_NOT_RESUMABLE",
                message="当前任务状态不允许恢复",
                detail=f"status={current.status}",
            )
        job.updated_at = _now()
        job.completed_at = None
        job.error_message = None
        job.cancel_requested = False
        return self._jobs.update_job(job)

    def is_cancel_requested(self, job_id: str) -> bool:
        return self.get_job(job_id).cancel_requested

    def append_event(self, job_id: str, event_type: AnalysisEventType, payload: dict[str, Any] | None = None) -> AnalysisEvent:
        self.get_job(job_id)
        event = AnalysisEvent(
            job_id=job_id,
            type=event_type,
            payload=payload or {},
            created_at=_now(),
            sequence=self._events.next_sequence(job_id),
        )
        return self._events.append_event(event)

    def get_events_after(self, job_id: str, sequence: int) -> list[AnalysisEvent]:
        self.get_job(job_id)
        return self._events.get_events_after(job_id, sequence)

    def put_artifact(self, job_id: str, artifact_type: str, payload: Any) -> AnalysisArtifact:
        self.get_job(job_id)
        artifact = AnalysisArtifact(
            job_id=job_id,
            artifact_type=artifact_type,
            payload=payload,
            created_at=_now(),
        )
        return self._artifacts.put_artifact(artifact)

    def has_artifact(self, job_id: str, artifact_type: str) -> bool:
        self.get_job(job_id)
        return bool(self._artifacts.list_artifacts(job_id, artifact_type))

    def get_artifact_payload(self, job_id: str, artifact_type: str) -> Any | None:
        self.get_job(job_id)
        artifacts = self._artifacts.list_artifacts(job_id, artifact_type)
        return artifacts[-1].payload if artifacts else None

    def get_snapshot(self, job_id: str) -> AnalysisJobSnapshot:
        job = self.get_job(job_id)
        events = self.get_events_after(job_id, 0)
        artifacts = self._artifacts.list_artifacts(job_id)
        by_type = {artifact.artifact_type: artifact.payload for artifact in artifacts}
        return AnalysisJobSnapshot(
            job=job,
            events=events,
            file_tree=[FileTreeNode.model_validate(item) for item in by_type.get("file_tree", [])],
            basic_files=[BasicFileSummary.model_validate(item) for item in by_type.get("basic_files", [])],
            core_files=[CoreFileSummary.model_validate(item) for item in by_type.get("core_files", [])],
            documents=[GeneratedDocument.model_validate(item) for item in by_type.get("documents", [])],
            result=AnalyzeRepoResponse.model_validate(by_type["result"]) if "result" in by_type else None,
        )

    def persist_run_details(
        self,
        job_id: str,
        *,
        agent_steps: list[AgentStep],
        tool_logs: list[ToolCallLog],
        llm_call_records: list[LLMCallRecord],
    ) -> None:
        self.get_job(job_id)
        persist = getattr(self._artifacts, "replace_run_details", None)
        if persist is not None:
            persist(
                job_id=job_id,
                agent_steps=agent_steps,
                tool_logs=tool_logs,
                llm_call_records=llm_call_records,
            )


def _now() -> str:
    return datetime.now(UTC).isoformat()


from app.db.repositories import create_default_analysis_job_repository


_repository = create_default_analysis_job_repository()
analysis_job_service = AnalysisJobService(
    job_repository=_repository,
    event_repository=_repository,
    artifact_repository=_repository,
)
