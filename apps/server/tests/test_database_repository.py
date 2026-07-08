import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import AgentStepRow, GeneratedDocumentRow, LlmCallRow, ToolCallRow
from app.db.repositories import SqlAnalysisJobRepository
from app.db.session import create_engine_for_url, init_db
from app.schemas.agent import AgentStep, GeneratedDocument, ToolCallLog
from app.services.analysis_job_service import AnalysisJobService
from app.services.llm_call_service import LLMCallRecord


pytestmark = pytest.mark.integration


@pytest.fixture
def db_service():
    """创建 SQL 持久化层的 AnalysisJobService。"""
    engine = create_engine_for_url("sqlite:///:memory:")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    repository = SqlAnalysisJobRepository(session_factory)
    service = AnalysisJobService(
        job_repository=repository,
        event_repository=repository,
        artifact_repository=repository,
    )
    return service, session_factory


def test_persists_jobs_events_and_artifacts_across_service_instances(db_service) -> None:
    service, session_factory = db_service
    job = service.create_job("https://github.com/owner/repo")
    service.update_status(job.id, "running", owner="owner", repo="repo")
    service.append_event(job.id, "job_started", {"repo_url": job.repo_url})
    service.append_event(job.id, "stage_started", {"stage": "clone"})
    document = GeneratedDocument(title="Overview", filename="01.md", path="generated_docs/demo/01.md", content="# Demo")
    service.put_artifact(job.id, "documents", [document.model_dump()])

    repository = SqlAnalysisJobRepository(session_factory)
    service2 = AnalysisJobService(
        job_repository=repository,
        event_repository=repository,
        artifact_repository=repository,
    )
    snapshot = service2.get_snapshot(job.id)

    assert snapshot.job.owner == "owner"
    assert [event.sequence for event in snapshot.events] == [1, 2]
    assert snapshot.documents[0].filename == "01.md"
    with session_factory() as session:
        rows = session.scalars(select(GeneratedDocumentRow).where(GeneratedDocumentRow.job_id == job.id)).all()
    assert len(rows) == 1
    assert rows[0].char_count == len("# Demo")


def test_persists_run_details_for_metrics_traceability(db_service) -> None:
    service, session_factory = db_service
    job = service.create_job("https://github.com/owner/repo")
    step = AgentStep(key="parse", title="Parse", status="success", description="Parse repo", duration_ms=3)
    tool_log = ToolCallLog(
        tool_provider="mcp",
        tool_name="parse_github_repo_url",
        permission="read",
        status="success",
        input_summary="repo",
        output_summary="owner/repo",
        input={"repo_url": "https://github.com/owner/repo"},
        output={"owner": "owner", "repo": "repo"},
        related_files=[],
        duration_ms=4,
        created_at="2026-07-01T00:00:00+00:00",
    )
    llm_record = LLMCallRecord(
        provider="openai",
        model="m",
        prompt_type="overview",
        duration_ms=5,
        status="success",
        input_tokens=12,
        output_tokens=8,
        total_tokens=20,
    )

    service.persist_run_details(
        job.id,
        agent_steps=[step],
        tool_logs=[tool_log],
        llm_call_records=[llm_record],
    )

    with session_factory() as session:
        assert len(session.scalars(select(AgentStepRow)).all()) == 1
        tool_rows = session.scalars(select(ToolCallRow)).all()
        assert len(tool_rows) == 1
        assert tool_rows[0].tool_provider == "mcp"
        llm_rows = session.scalars(select(LlmCallRow)).all()
        assert len(llm_rows) == 1
        assert llm_rows[0].input_tokens == 12
        assert llm_rows[0].output_tokens == 8
        assert llm_rows[0].total_tokens == 20