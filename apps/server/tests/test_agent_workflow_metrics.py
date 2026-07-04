import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError
from app.agent import workflow
from app.db.models import AnalysisJobRow
from app.db.session import create_engine_for_url, init_db
from app.mcp.schemas import McpTool, McpToolCallResult
from app.services import history_service
from app.services.analysis_job_repository import InMemoryAnalysisJobRepository
from app.services.analysis_job_service import AnalysisJobService
from app.services.mcp_tool_service import McpToolService


class AgentWorkflowMetricsTests(unittest.TestCase):
    def test_real_analysis_response_contains_metrics_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = root / "repo"
            repo_root.mkdir()
            (repo_root / "README.md").write_text("a" * 20, encoding="utf-8")
            (repo_root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
            (repo_root / "src").mkdir()
            (repo_root / "src" / "main.ts").write_text("b" * 30, encoding="utf-8")
            (repo_root / "app").mkdir()
            (repo_root / "app" / "main.py").write_text("print('demo')", encoding="utf-8")
            generated_docs_path = root / "generated_docs"
            metrics_path = root / "data" / "metrics.jsonl"
            history_path = root / "data" / "history.json"
            engine = create_engine_for_url("sqlite:///:memory:")
            init_db(engine)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

            original_settings = workflow.settings
            original_clone_repository = workflow.clone_repository
            original_generate_markdown_documents = workflow.generate_markdown_documents
            original_history_session = history_service.SessionLocal
            workflow.settings = SimpleNamespace(
                temp_repo_path=root / "temp_repos",
                generated_docs_path=generated_docs_path,
                metrics_path=metrics_path,
                history_path=history_path,
                llm_provider="openai",
                llm_api_key="test-api-key",
                llm_model="test-model",
                llm_base_url=None,
                max_file_tree_depth=4,
                max_file_tree_entries=100,
                max_basic_file_bytes=20_000,
                max_core_files=2,
                max_core_file_bytes=10,
            )
            workflow.clone_repository = lambda parsed_repo, temp_repo_path: repo_root
            workflow.generate_markdown_documents = self._fake_markdown_documents
            history_service.SessionLocal = session_factory
            try:
                response = workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository
                workflow.generate_markdown_documents = original_generate_markdown_documents
                history_service.SessionLocal = original_history_session

            metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8").splitlines()[-1])
            history_records = history_service.list_history_records(history_file=history_path, session_factory=session_factory)
            with session_factory() as session:
                history_row = session.get(AnalysisJobRow, history_records[0].id)

        self.assertEqual(response.metrics.candidate_core_files, 4)
        self.assertEqual(response.metrics.total_files, 4)
        self.assertEqual(response.metrics.ignored_dirs, 0)
        self.assertEqual(response.metrics.selected_core_files, 2)
        self.assertEqual(response.metrics.read_files, 2)
        self.assertEqual(response.metrics.truncated_files, 2)
        self.assertEqual(response.metrics.final_context_chars, 20)
        self.assertEqual(response.context_quality_report.candidate_file_count, 4)
        self.assertEqual(response.context_quality_report.selected_file_count, 2)
        self.assertEqual(response.context_quality_report.omitted_candidate_count, 2)
        self.assertEqual(response.context_quality_report.context_char_count, 20)
        self.assertEqual(response.context_quality_report.raw_candidate_chars, response.metrics.raw_candidate_chars)
        self.assertEqual(response.context_quality_report.compression_ratio, response.metrics.context_compression_ratio)
        self.assertTrue(response.context_quality_report.budget_limit_reached)
        self.assertEqual(response.context_quality_report.selected_files, ["README.md", "package.json"])
        self.assertEqual(response.context_quality_report.directory_coverage[0].directory, ".")
        self.assertEqual(response.context_quality_report.directory_coverage[0].selected_file_count, 2)
        self.assertEqual(response.context_quality_report.omitted_candidates[0].path, "app/main.py")
        self.assertGreater(response.metrics.raw_candidate_chars, response.metrics.final_context_chars)
        self.assertGreater(response.metrics.context_compression_ratio, 0)
        self.assertLess(response.metrics.context_compression_ratio, 1)
        self.assertEqual(response.metrics.mock_doc_count, 1)
        self.assertGreater(response.metrics.mock_doc_total_chars, 0)
        self.assertGreaterEqual(response.metrics.analysis_duration_ms, 0)
        self.assertEqual(response.metrics.agent_step_count, len(response.agent_steps))
        self.assertEqual(response.metrics.agent_success_step_count, 9)
        self.assertEqual(response.metrics.agent_failed_step_count, 0)
        self.assertEqual(response.metrics.agent_skipped_step_count, 1)
        self.assertEqual(response.metrics.tool_call_count, len(response.tool_logs))
        self.assertEqual(response.metrics.tool_success_count, 9)
        self.assertEqual(response.metrics.tool_failed_count, 0)
        self.assertTrue(all(log.tool_provider == "builtin" for log in response.tool_logs))
        self.assertTrue(all(log.permission for log in response.tool_logs))
        llm_tool_log = next(log for log in response.tool_logs if log.tool_name == "llm_service.generate_markdown_documents")
        self.assertEqual(llm_tool_log.permission, "llm")
        self.assertIn("document_count", llm_tool_log.input_schema["properties"])
        self.assertGreaterEqual(response.metrics.avg_tool_duration_ms, 0)
        self.assertGreaterEqual(response.metrics.max_tool_duration_ms, response.metrics.avg_tool_duration_ms)
        self.assertGreaterEqual(response.metrics.total_tool_duration_ms, response.metrics.max_tool_duration_ms)
        self.assertTrue(all(step.duration_ms >= 0 for step in response.agent_steps))
        self.assertTrue(all(step.step_id for step in response.agent_steps))
        self.assertTrue(all(step.completed_at for step in response.agent_steps))
        self.assertIn("success", {step.status for step in response.agent_steps})
        self.assertIn("skipped", {step.status for step in response.agent_steps})
        mcp_skipped_log = next(log for log in response.tool_logs if log.tool_name == "fetch_github_mcp_context")
        self.assertEqual(mcp_skipped_log.status, "skipped")
        self.assertEqual(mcp_skipped_log.permission, "read")
        self.assertEqual(response.result_evaluation.document_count, 1)
        self.assertEqual(response.result_evaluation.valid_reference_count, 1)
        self.assertEqual(response.result_evaluation.invalid_reference_count, 0)
        self.assertEqual(response.result_evaluation.textcitation_score, 1)
        self.assertEqual(response.result_evaluation.coverage_score, 0.5)
        self.assertLess(response.result_evaluation.usefulness_score, 1)
        evaluation_log = next(log for log in response.tool_logs if log.tool_name == "evaluate_generated_documents")
        self.assertEqual(evaluation_log.permission, "read")
        self.assertEqual(evaluation_log.output["textcitation_score"], 1)
        self.assertIn("README.md", response.tool_logs[3].output["read_files"])
        select_log = next(log for log in response.tool_logs if log.tool_name == "select_core_files")
        self.assertIn("selected_files", select_log.output)
        self.assertTrue(select_log.related_files)
        context_log = next(log for log in response.tool_logs if log.tool_name == "build_analysis_context")
        self.assertIn("used_for_context", context_log.output)
        self.assertEqual(metrics_payload["operation"], "agent_analyze")
        self.assertEqual(metrics_payload["total_files"], response.metrics.total_files)
        self.assertEqual(metrics_payload["ignored_dirs"], response.metrics.ignored_dirs)
        self.assertEqual(metrics_payload["mock_doc_count"], 1)
        self.assertEqual(metrics_payload["selected_core_files"], 2)
        self.assertFalse(metrics_payload["used_mock_ai"])
        self.assertEqual(metrics_payload["llm_call_count"], 1)
        self.assertEqual(metrics_payload["prompt_template_count"], 7)
        self.assertEqual(metrics_payload["generated_doc_count"], 1)
        self.assertGreater(metrics_payload["generated_doc_total_chars"], 0)
        self.assertEqual(metrics_payload["interview_question_count"], 0)
        self.assertEqual(metrics_payload["agent_step_count"], response.metrics.agent_step_count)
        self.assertEqual(metrics_payload["tool_call_count"], response.metrics.tool_call_count)
        self.assertEqual(metrics_payload["tool_success_count"], response.metrics.tool_success_count)
        self.assertEqual(metrics_payload["tool_failed_count"], response.metrics.tool_failed_count)
        self.assertEqual(metrics_payload["avg_tool_duration_ms"], response.metrics.avg_tool_duration_ms)
        self.assertEqual(len(history_records), 1)
        self.assertEqual(history_records[0].repo_url, "https://github.com/owner/repo")
        self.assertEqual(history_records[0].status, "success")
        self.assertEqual(history_records[0].docs_dir, response.docs_dir)
        self.assertEqual(history_records[0].core_files_count, len(response.core_files))
        self.assertEqual(history_row.metrics_json["total_files"], response.metrics.total_files)
        self.assertEqual(history_row.metrics_json["tool_call_count"], response.metrics.tool_call_count)
        self.assertFalse(history_path.exists())

    def test_job_workflow_emits_metrics_updated_with_scan_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = self._create_repo(root)
            (repo_root / "node_modules").mkdir()
            (repo_root / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")

            repository = InMemoryAnalysisJobRepository()
            job_service = AnalysisJobService(
                job_repository=repository,
                event_repository=repository,
                artifact_repository=repository,
            )
            job = job_service.create_job("https://github.com/owner/repo")

            original_settings = workflow.settings
            original_clone_repository = workflow.clone_repository
            original_generate_markdown_documents = workflow.generate_markdown_documents
            workflow.settings = SimpleNamespace(
                temp_repo_path=root / "temp_repos",
                generated_docs_path=root / "generated_docs",
                metrics_path=root / "data" / "metrics.jsonl",
                history_path=root / "data" / "history.json",
                llm_provider="openai",
                llm_api_key="test-api-key",
                llm_model="test-model",
                llm_base_url=None,
                max_file_tree_depth=4,
                max_file_tree_entries=100,
                max_basic_file_bytes=20_000,
                max_core_files=2,
                max_core_file_bytes=20,
            )
            workflow.clone_repository = lambda parsed_repo, temp_repo_path: repo_root
            workflow.generate_markdown_documents = self._fake_markdown_documents
            try:
                workflow.run_codebase_analysis_job(
                    job_id=job.id,
                    repo_url="https://github.com/owner/repo",
                    job_service=job_service,
                )
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository
                workflow.generate_markdown_documents = original_generate_markdown_documents

            events = job_service.get_events_after(job.id, 0)
            metrics_events = [event for event in events if event.type == "metrics_updated"]
            repo_loaded_event = next(event for event in events if event.payload.get("key") == "repo_loaded")
            completed_event = next(event for event in events if event.type == "job_completed")

        self.assertGreaterEqual(len(metrics_events), 1)
        self.assertEqual(metrics_events[0].payload["metrics"]["total_files"], 3)
        self.assertEqual(metrics_events[0].payload["metrics"]["ignored_dirs"], 1)
        self.assertEqual(repo_loaded_event.payload["context_quality_report"]["selected_file_count"], 2)
        self.assertEqual(repo_loaded_event.payload["context_quality_report"]["omitted_candidate_count"], 1)
        self.assertEqual(completed_event.payload["metrics"]["total_files"], 3)
        self.assertEqual(completed_event.payload["metrics"]["ignored_dirs"], 1)
        self.assertEqual(completed_event.payload["result"]["result_evaluation"]["document_count"], 7)
        self.assertEqual(completed_event.payload["result"]["result_evaluation"]["textcitation_score"], 1)

    def test_workflow_merges_github_mcp_context_before_llm_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = self._create_repo(root)
            engine = create_engine_for_url("sqlite:///:memory:")
            init_db(engine)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

            original_settings = workflow.settings
            original_clone_repository = workflow.clone_repository
            original_generate_markdown_documents = workflow.generate_markdown_documents
            original_github_mcp_service = workflow._github_mcp_service
            original_history_session = history_service.SessionLocal
            workflow.settings = SimpleNamespace(
                temp_repo_path=root / "temp_repos",
                generated_docs_path=root / "generated_docs",
                metrics_path=root / "data" / "metrics.jsonl",
                history_path=root / "data" / "history.json",
                llm_provider="openai",
                llm_api_key="test-api-key",
                llm_model="test-model",
                llm_base_url=None,
                max_file_tree_depth=4,
                max_file_tree_entries=100,
                max_basic_file_bytes=20_000,
                max_core_files=2,
                max_core_file_bytes=20,
                mcp_config_file=None,
                mcp_readonly=True,
            )
            workflow.clone_repository = lambda parsed_repo, temp_repo_path: repo_root
            workflow.generate_markdown_documents = self._fake_markdown_documents_expect_github_context
            workflow._github_mcp_service = lambda: McpToolService(
                client=_FakeGithubMcpClient(),
                server_name="github",
                allowed_tools={"list_issues", "list_pull_requests", "list_commits"},
            )
            history_service.SessionLocal = session_factory
            try:
                response = workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository
                workflow.generate_markdown_documents = original_generate_markdown_documents
                workflow._github_mcp_service = original_github_mcp_service
                history_service.SessionLocal = original_history_session

        self.assertTrue(any(log.tool_name == "fetch_github_mcp_context" for log in response.tool_logs))
        self.assertTrue(any(log.tool_name == "mcp.github.list_issues" for log in response.tool_logs))
        self.assertEqual(response.metrics.agent_skipped_step_count, 0)

    def test_analysis_requires_llm_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = self._create_repo(root)
            generated_docs_path = root / "generated_docs"
            metrics_path = root / "data" / "metrics.jsonl"

            original_settings = workflow.settings
            original_clone_repository = workflow.clone_repository
            original_generate_markdown_documents = workflow.generate_markdown_documents
            workflow.settings = SimpleNamespace(
                temp_repo_path=root / "temp_repos",
                generated_docs_path=generated_docs_path,
                metrics_path=metrics_path,
                history_path=root / "data" / "history.json",
                mock_mode=False,
                openai_api_key=None,
                openai_model="test-model",
                max_file_tree_depth=4,
                max_file_tree_entries=100,
                max_basic_file_bytes=20_000,
                max_core_files=2,
                max_core_file_bytes=20,
            )
            workflow.clone_repository = lambda parsed_repo, temp_repo_path: repo_root
            workflow.generate_markdown_documents = self._fail_if_called
            try:
                with self.assertRaises(AppError) as raised:
                    workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository
                workflow.generate_markdown_documents = original_generate_markdown_documents

        self.assertEqual(raised.exception.code, "LLM_API_KEY_MISSING")
        self.assertEqual(raised.exception.status_code, 400)

    def test_analysis_uses_llm_service_when_api_key_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = self._create_repo(root)
            generated_docs_path = root / "generated_docs"
            metrics_path = root / "data" / "metrics.jsonl"

            original_settings = workflow.settings
            original_clone_repository = workflow.clone_repository
            original_generate_markdown_documents = workflow.generate_markdown_documents
            workflow.settings = SimpleNamespace(
                temp_repo_path=root / "temp_repos",
                generated_docs_path=generated_docs_path,
                metrics_path=metrics_path,
                history_path=root / "data" / "history.json",
                mock_mode=False,
                llm_provider="deepseek",
                llm_api_key="test-api-key",
                llm_model="deepseek-v4-flash",
                llm_base_url="https://api.deepseek.com",
                max_file_tree_depth=4,
                max_file_tree_entries=100,
                max_basic_file_bytes=20_000,
                max_core_files=2,
                max_core_file_bytes=20,
            )
            workflow.clone_repository = lambda parsed_repo, temp_repo_path: repo_root
            workflow.generate_markdown_documents = self._fake_markdown_documents
            try:
                response = workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository
                workflow.generate_markdown_documents = original_generate_markdown_documents

            metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8").splitlines()[-1])

        self.assertFalse(response.mock_mode)
        self.assertEqual(response.documents[0].content, "# Real AI Doc\n\n引用 `README.md`。")
        self.assertEqual(metrics_payload["operation"], "agent_analyze")
        self.assertFalse(metrics_payload["used_mock_ai"])
        self.assertEqual(metrics_payload["provider"], "deepseek")
        self.assertEqual(metrics_payload["model"], "deepseek-v4-flash")
        self.assertEqual(metrics_payload["llm_call_count"], 1)
        self.assertEqual(metrics_payload["llm_success_count"], 1)
        self.assertEqual(metrics_payload["llm_total_duration_ms"], 5)
        self.assertEqual(metrics_payload["prompt_template_count"], 7)
        self.assertEqual(metrics_payload["generated_doc_count"], 1)
        self.assertEqual(metrics_payload["referenced_file_path_count"], 1)
        self.assertEqual(metrics_payload["interview_question_count"], 0)

    def test_analysis_returns_structured_error_when_llm_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_root = self._create_repo(root)

            original_settings = workflow.settings
            original_clone_repository = workflow.clone_repository
            original_generate_markdown_documents = workflow.generate_markdown_documents
            workflow.settings = SimpleNamespace(
                temp_repo_path=root / "temp_repos",
                generated_docs_path=root / "generated_docs",
                metrics_path=root / "data" / "metrics.jsonl",
                history_path=root / "data" / "history.json",
                mock_mode=False,
                openai_api_key="test-api-key",
                openai_model="test-model",
                max_file_tree_depth=4,
                max_file_tree_entries=100,
                max_basic_file_bytes=20_000,
                max_core_files=2,
                max_core_file_bytes=20,
            )
            workflow.clone_repository = lambda parsed_repo, temp_repo_path: repo_root
            workflow.generate_markdown_documents = self._raise_llm_error
            try:
                with self.assertRaises(AppError) as raised:
                    workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository
                workflow.generate_markdown_documents = original_generate_markdown_documents

        self.assertEqual(raised.exception.code, "LLM_CALL_FAILED")
        self.assertEqual(raised.exception.status_code, 502)
        failed_steps = [step for step in raised.exception.agent_steps if step.status == "failed"]
        self.assertEqual(failed_steps[-1].key, "generate_real_ai_documents")
        self.assertEqual(failed_steps[-1].error_message, "AI 文档生成失败")
        self.assertEqual(raised.exception.tool_logs[-1].status, "failed")
        self.assertEqual(raised.exception.tool_logs[-1].error_message, "boom")

    def _create_repo(self, root: Path) -> Path:
        repo_root = root / "repo"
        repo_root.mkdir()
        (repo_root / "README.md").write_text("demo readme", encoding="utf-8")
        (repo_root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
        (repo_root / "src").mkdir()
        (repo_root / "src" / "main.ts").write_text("console.log('demo')", encoding="utf-8")
        return repo_root

    def _fail_if_called(self, **_: object) -> list[tuple[str, str, str]]:
        raise AssertionError("generate_markdown_documents should not be called")

    def _fake_markdown_documents(self, *, recorder=None, **_: object) -> list[tuple[str, str, str]]:
        if recorder is not None:
            recorder.record(prompt_type="真实文档", duration_ms=5, status="success")
        return [("真实文档", "01-项目概览.md", "# Real AI Doc\n\n引用 `README.md`。")]

    def _fake_markdown_documents_expect_github_context(self, *, context: str, recorder=None, **_: object) -> list[tuple[str, str, str]]:
        self.assertIn("## GitHub 协作上下文", context)
        self.assertIn("#7 Improve onboarding docs", context)
        if recorder is not None:
            recorder.record(prompt_type="真实文档", duration_ms=5, status="success")
        return [("真实文档", "01-项目概览.md", "# Real AI Doc\n\n## Context\n\n引用 `README.md`。")]

    def _raise_llm_error(self, **_: object) -> list[tuple[str, str, str]]:
        raise AppError(
            status_code=502,
            code="LLM_CALL_FAILED",
            message="AI 文档生成失败",
            detail="boom",
        )


class _FakeGithubMcpClient:
    def list_tools(self, server_name: str) -> list[McpTool]:
        return [
            McpTool(name="list_issues"),
            McpTool(name="list_pull_requests"),
            McpTool(name="list_commits"),
        ]

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> McpToolCallResult:
        payloads = {
            "list_issues": [{"number": 7, "title": "Improve onboarding docs", "state": "open"}],
            "list_pull_requests": [{"number": 9, "title": "Refactor workflow", "state": "open"}],
            "list_commits": [{"sha": "abc123", "commit": {"message": "Improve docs"}}],
        }
        return McpToolCallResult(content=payloads[tool_name], summary=f"Returned {tool_name}")


if __name__ == "__main__":
    unittest.main()
