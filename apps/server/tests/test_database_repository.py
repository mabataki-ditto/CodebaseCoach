import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import AgentStepRow, GeneratedDocumentRow, LlmCallRow, ToolCallRow
from app.db.repositories import SqlAnalysisJobRepository
from app.db.session import create_engine_for_url, init_db
from app.schemas.agent import AgentStep, GeneratedDocument, ToolCallLog
from app.services.analysis_job_service import AnalysisJobService
from app.services.llm_call_service import LLMCallRecord


class DatabaseAnalysisJobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine_for_url("sqlite:///:memory:")
        init_db(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        self.repository = SqlAnalysisJobRepository(self.session_factory)
        self.service = AnalysisJobService(
            job_repository=self.repository,
            event_repository=self.repository,
            artifact_repository=self.repository,
        )

    def test_persists_jobs_events_and_artifacts_across_service_instances(self) -> None:
        job = self.service.create_job("https://github.com/owner/repo")
        self.service.update_status(job.id, "running", owner="owner", repo="repo")
        self.service.append_event(job.id, "job_started", {"repo_url": job.repo_url})
        self.service.append_event(job.id, "stage_started", {"stage": "clone"})
        document = GeneratedDocument(title="Overview", filename="01.md", path="generated_docs/demo/01.md", content="# Demo")
        self.service.put_artifact(job.id, "documents", [document.model_dump()])

        repository = SqlAnalysisJobRepository(self.session_factory)
        service = AnalysisJobService(
            job_repository=repository,
            event_repository=repository,
            artifact_repository=repository,
        )
        snapshot = service.get_snapshot(job.id)

        self.assertEqual(snapshot.job.owner, "owner")
        self.assertEqual([event.sequence for event in snapshot.events], [1, 2])
        self.assertEqual(snapshot.documents[0].filename, "01.md")
        with self.session_factory() as session:
            rows = session.scalars(select(GeneratedDocumentRow).where(GeneratedDocumentRow.job_id == job.id)).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].char_count, len("# Demo"))

    def test_persists_run_details_for_metrics_traceability(self) -> None:
        job = self.service.create_job("https://github.com/owner/repo")
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

        self.service.persist_run_details(
            job.id,
            agent_steps=[step],
            tool_logs=[tool_log],
            llm_call_records=[llm_record],
        )

        with self.session_factory() as session:
            self.assertEqual(len(session.scalars(select(AgentStepRow)).all()), 1)
            tool_rows = session.scalars(select(ToolCallRow)).all()
            self.assertEqual(len(tool_rows), 1)
            self.assertEqual(tool_rows[0].tool_provider, "mcp")
            llm_rows = session.scalars(select(LlmCallRow)).all()
            self.assertEqual(len(llm_rows), 1)
            self.assertEqual(llm_rows[0].input_tokens, 12)
            self.assertEqual(llm_rows[0].output_tokens, 8)
            self.assertEqual(llm_rows[0].total_tokens, 20)


if __name__ == "__main__":
    unittest.main()
