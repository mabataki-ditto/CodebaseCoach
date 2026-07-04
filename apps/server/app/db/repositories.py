from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AgentStepRow,
    AnalysisArtifactRow,
    AnalysisEventRow,
    AnalysisJobRow,
    GeneratedDocumentRow,
    LlmCallRow,
    RepositoryRow,
    ToolCallRow,
)
from app.db.session import SessionLocal, init_db
from app.schemas.agent import AgentStep, GeneratedDocument, ToolCallLog
from app.schemas.analysis_job import AnalysisArtifact, AnalysisEvent, AnalysisJob
from app.schemas.metrics import MockAnalysisMetrics
from app.services.analysis_job_repository import (
    AnalysisArtifactRepository,
    AnalysisEventRepository,
    AnalysisJobRepository,
)
from app.services.llm_call_service import LLMCallRecord


class SqlAnalysisJobRepository(AnalysisJobRepository, AnalysisEventRepository, AnalysisArtifactRepository):
    def __init__(self, session_factory: sessionmaker[Session] | Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def create_job(self, job: AnalysisJob) -> AnalysisJob:
        with self._session_factory() as session:
            repository = _get_or_create_repository(session, repo_url=job.repo_url, owner=job.owner, repo=job.repo)
            row = AnalysisJobRow(
                id=job.id,
                repository_id=repository.id,
                repo_url=job.repo_url,
                owner=job.owner,
                repo=job.repo,
                status=job.status,
                mock_mode=job.mock_mode,
                llm_provider=_metrics_provider(job.metrics),
                llm_model=_metrics_model(job.metrics),
                docs_dir=job.docs_dir,
                core_files_count=job.core_files_count,
                error_message=job.error_message,
                metrics_json=_dump_metrics(job.metrics),
                cancel_requested=job.cancel_requested,
                created_at=job.created_at,
                updated_at=job.updated_at,
                completed_at=job.completed_at,
            )
            session.add(row)
            session.commit()
            return _job_from_row(row)

    def get_job(self, job_id: str) -> AnalysisJob | None:
        with self._session_factory() as session:
            row = session.get(AnalysisJobRow, job_id)
            return _job_from_row(row) if row else None

    def update_job(self, job: AnalysisJob) -> AnalysisJob:
        with self._session_factory() as session:
            row = session.get(AnalysisJobRow, job.id)
            if row is None:
                return self.create_job(job)
            repository = _get_or_create_repository(session, repo_url=job.repo_url, owner=job.owner, repo=job.repo)
            row.repository_id = repository.id
            row.repo_url = job.repo_url
            row.owner = job.owner
            row.repo = job.repo
            row.status = job.status
            row.mock_mode = job.mock_mode
            row.llm_provider = _metrics_provider(job.metrics)
            row.llm_model = _metrics_model(job.metrics)
            row.docs_dir = job.docs_dir
            row.core_files_count = job.core_files_count
            row.error_message = job.error_message
            row.metrics_json = _dump_metrics(job.metrics)
            row.cancel_requested = job.cancel_requested
            row.updated_at = job.updated_at
            row.completed_at = job.completed_at
            session.commit()
            session.refresh(row)
            return _job_from_row(row)

    def append_event(self, event: AnalysisEvent) -> AnalysisEvent:
        with self._session_factory() as session:
            max_sequence = session.scalar(
                select(func.max(AnalysisEventRow.sequence)).where(AnalysisEventRow.job_id == event.job_id)
            )
            row = AnalysisEventRow(
                id=event.id,
                job_id=event.job_id,
                sequence=int(max_sequence or 0) + 1,
                type=event.type,
                payload_json=event.payload,
                created_at=event.created_at,
            )
            session.add(row)
            session.commit()
            return _event_from_row(row)

    def get_events_after(self, job_id: str, sequence: int) -> list[AnalysisEvent]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AnalysisEventRow)
                .where(AnalysisEventRow.job_id == job_id, AnalysisEventRow.sequence > sequence)
                .order_by(AnalysisEventRow.sequence)
            ).all()
            return [_event_from_row(row) for row in rows]

    def next_sequence(self, job_id: str) -> int:
        with self._session_factory() as session:
            max_sequence = session.scalar(
                select(func.max(AnalysisEventRow.sequence)).where(AnalysisEventRow.job_id == job_id)
            )
            return int(max_sequence or 0) + 1

    def put_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        with self._session_factory() as session:
            row = session.scalar(
                select(AnalysisArtifactRow).where(
                    AnalysisArtifactRow.job_id == artifact.job_id,
                    AnalysisArtifactRow.artifact_type == artifact.artifact_type,
                )
            )
            now = artifact.created_at
            if row is None:
                row = AnalysisArtifactRow(
                    id=artifact.id,
                    job_id=artifact.job_id,
                    artifact_type=artifact.artifact_type,
                    payload_json=artifact.payload,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.payload_json = artifact.payload
                row.updated_at = now
            if artifact.artifact_type == "documents":
                _replace_generated_documents(session, artifact.job_id, artifact.payload, now)
            session.commit()
            session.refresh(row)
            return _artifact_from_row(row)

    def list_artifacts(self, job_id: str, artifact_type: str | None = None) -> list[AnalysisArtifact]:
        with self._session_factory() as session:
            query = select(AnalysisArtifactRow).where(AnalysisArtifactRow.job_id == job_id)
            if artifact_type is not None:
                query = query.where(AnalysisArtifactRow.artifact_type == artifact_type)
            rows = session.scalars(query.order_by(AnalysisArtifactRow.created_at)).all()
            return [_artifact_from_row(row) for row in rows]

    def replace_run_details(
        self,
        *,
        job_id: str,
        agent_steps: list[AgentStep],
        tool_logs: list[ToolCallLog],
        llm_call_records: list[LLMCallRecord],
    ) -> None:
        now = _now()
        with self._session_factory() as session:
            session.execute(delete(AgentStepRow).where(AgentStepRow.job_id == job_id))
            session.execute(delete(ToolCallRow).where(ToolCallRow.job_id == job_id))
            session.execute(delete(LlmCallRow).where(LlmCallRow.job_id == job_id))
            for step in agent_steps:
                session.add(
                    AgentStepRow(
                        id=step.id or step.step_id,
                        job_id=job_id,
                        step_id=step.step_id,
                        key=step.key,
                        title=step.title,
                        status=step.status,
                        description=step.description,
                        started_at=step.started_at,
                        ended_at=step.ended_at,
                        completed_at=step.completed_at,
                        duration_ms=step.duration_ms,
                        error_message=step.error_message,
                        metadata_json=step.metadata,
                        created_at=step.started_at or now,
                        updated_at=step.completed_at or now,
                    )
                )
            for log in tool_logs:
                session.add(
                    ToolCallRow(
                        id=log.id,
                        job_id=job_id,
                        step_id=None,
                        tool_provider=log.tool_provider,
                        tool_name=log.tool_name,
                        status=log.status,
                        input_summary=log.input_summary,
                        output_summary=log.output_summary,
                        input_json=log.input,
                        output_json=log.output,
                        related_files_json=log.related_files,
                        duration_ms=log.duration_ms,
                        error_message=log.error_message,
                        created_at=log.created_at,
                    )
                )
            for record in llm_call_records:
                session.add(
                    LlmCallRow(
                        id=uuid4().hex,
                        job_id=job_id,
                        provider=record.provider,
                        model=record.model,
                        prompt_type=record.prompt_type,
                        duration_ms=record.duration_ms,
                        status=record.status,
                        error_message=record.error_message,
                        input_tokens=record.input_tokens,
                        output_tokens=record.output_tokens,
                        total_tokens=record.total_tokens,
                        created_at=now,
                    )
                )
            session.commit()


def create_default_analysis_job_repository() -> SqlAnalysisJobRepository:
    init_db()
    return SqlAnalysisJobRepository()


def _job_from_row(row: AnalysisJobRow) -> AnalysisJob:
    return AnalysisJob(
        id=row.id,
        repo_url=row.repo_url,
        owner=row.owner,
        repo=row.repo,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
        docs_dir=row.docs_dir,
        core_files_count=row.core_files_count,
        error_message=row.error_message,
        metrics=MockAnalysisMetrics.model_validate(row.metrics_json) if row.metrics_json else None,
        mock_mode=row.mock_mode,
        cancel_requested=row.cancel_requested,
    )


def _event_from_row(row: AnalysisEventRow) -> AnalysisEvent:
    return AnalysisEvent(
        id=row.id,
        job_id=row.job_id,
        type=row.type,
        payload=row.payload_json,
        created_at=row.created_at,
        sequence=row.sequence,
    )


def _artifact_from_row(row: AnalysisArtifactRow) -> AnalysisArtifact:
    return AnalysisArtifact(
        id=row.id,
        job_id=row.job_id,
        artifact_type=row.artifact_type,
        payload=row.payload_json,
        created_at=row.created_at,
    )


def _get_or_create_repository(session: Session, *, repo_url: str, owner: str, repo: str) -> RepositoryRow:
    repository = session.scalar(select(RepositoryRow).where(RepositoryRow.repo_url == repo_url))
    now = _now()
    if repository is not None:
        if owner:
            repository.owner = owner
        if repo:
            repository.repo = repo
        repository.updated_at = now
        return repository
    repository = RepositoryRow(
        id=uuid4().hex,
        repo_url=repo_url,
        owner=owner,
        repo=repo,
        created_at=now,
        updated_at=now,
    )
    session.add(repository)
    return repository


def _replace_generated_documents(session: Session, job_id: str, documents: Any, now: str) -> None:
    session.execute(delete(GeneratedDocumentRow).where(GeneratedDocumentRow.job_id == job_id))
    if not isinstance(documents, list):
        return
    for item in documents:
        document = GeneratedDocument.model_validate(item)
        content = document.content or ""
        session.add(
            GeneratedDocumentRow(
                id=uuid4().hex,
                job_id=job_id,
                title=document.title,
                filename=document.filename,
                path=document.path,
                doc_type=_doc_type(document.filename),
                char_count=len(content),
                word_count=_count_words(content),
                created_at=now,
                updated_at=now,
            )
        )


def _dump_metrics(metrics: Any | None) -> dict | None:
    if metrics is None:
        return None
    if hasattr(metrics, "model_dump"):
        return metrics.model_dump()
    if isinstance(metrics, dict):
        return metrics
    return None


def _metrics_provider(metrics: Any | None) -> str:
    return str(getattr(metrics, "provider", "") or "")


def _metrics_model(metrics: Any | None) -> str:
    return str(getattr(metrics, "model", "") or "")


def _doc_type(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    return stem.split("-", 1)[-1] if "-" in stem else stem


def _count_words(content: str) -> int:
    return len(content.split())


def _now() -> str:
    return datetime.now(UTC).isoformat()
