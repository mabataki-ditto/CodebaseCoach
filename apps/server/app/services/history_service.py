from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AnalysisJobRow
from app.db.repositories import SqlAnalysisJobRepository
from app.db.session import SessionLocal
from app.schemas.analysis_job import AnalysisJob
from app.schemas.history import HistoryRecord
from app.schemas.metrics import MockAnalysisMetrics


def list_history_records(
    *,
    history_file: Path | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> list[HistoryRecord]:
    session_factory = session_factory or SessionLocal
    with session_factory() as session:
        rows = session.scalars(select(AnalysisJobRow).order_by(AnalysisJobRow.created_at.desc())).all()
        return [_history_from_job(row) for row in rows]


def add_history_record(
    *,
    history_file: Path,
    repo_url: str,
    owner: str,
    repo: str,
    status: str,
    created_at: str,
    completed_at: str | None,
    docs_dir: str = "",
    core_files_count: int = 0,
    error_message: str | None = None,
    mock_mode: bool = True,
    metrics: MockAnalysisMetrics | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> HistoryRecord:
    session_factory = session_factory or SessionLocal
    record_id = uuid4().hex
    repository = SqlAnalysisJobRepository(session_factory)
    repository.create_job(
        AnalysisJob(
            id=record_id,
            repo_url=repo_url,
            owner=owner,
            repo=repo,
            status=status,
            created_at=created_at,
            updated_at=completed_at or created_at,
            completed_at=completed_at,
            docs_dir=docs_dir,
            core_files_count=core_files_count,
            error_message=error_message,
            metrics=metrics,
            mock_mode=mock_mode,
        )
    )
    record = HistoryRecord(
        id=record_id,
        repo_url=repo_url,
        owner=owner,
        repo=repo,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        docs_dir=docs_dir,
        core_files_count=core_files_count,
        error_message=error_message,
        mock_mode=mock_mode,
    )
    return record


def delete_history_record(
    *,
    history_file: Path | None = None,
    record_id: str,
    session_factory: sessionmaker[Session] | None = None,
) -> bool:
    session_factory = session_factory or SessionLocal
    with session_factory() as session:
        result = session.execute(delete(AnalysisJobRow).where(AnalysisJobRow.id == record_id))
        session.commit()
        return bool(result.rowcount)


def get_history_record(
    *,
    history_file: Path | None = None,
    record_id: str,
    session_factory: sessionmaker[Session] | None = None,
) -> HistoryRecord | None:
    session_factory = session_factory or SessionLocal
    with session_factory() as session:
        row = session.get(AnalysisJobRow, record_id)
        return _history_from_job(row) if row else None


def _history_from_job(row: AnalysisJobRow) -> HistoryRecord:
    return HistoryRecord(
        id=row.id,
        repo_url=row.repo_url,
        owner=row.owner,
        repo=row.repo,
        status=row.status,
        created_at=row.created_at,
        completed_at=row.completed_at,
        docs_dir=row.docs_dir,
        core_files_count=row.core_files_count,
        error_message=row.error_message,
        mock_mode=row.mock_mode,
    )
