import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.core.errors import AppError
from app.agent import workflow
from app.services.analysis_job_repository import InMemoryAnalysisJobRepository
from app.services.analysis_job_service import AnalysisJobService


class AgentWorkflowMetricsTests(unittest.TestCase):
    def test_mock_analysis_response_contains_metrics_without_network(self) -> None:
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

            original_settings = workflow.settings
            original_clone_repository = workflow.clone_repository
            workflow.settings = SimpleNamespace(
                temp_repo_path=root / "temp_repos",
                generated_docs_path=generated_docs_path,
                metrics_path=metrics_path,
                history_path=history_path,
                mock_mode=True,
                openai_api_key=None,
                openai_model="test-model",
                max_file_tree_depth=4,
                max_file_tree_entries=100,
                max_basic_file_bytes=20_000,
                max_core_files=2,
                max_core_file_bytes=10,
            )
            workflow.clone_repository = lambda parsed_repo, temp_repo_path: repo_root
            try:
                response = workflow.run_mock_codebase_analysis_workflow("https://github.com/owner/repo")
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository

            metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8").splitlines()[-1])
            history_payload = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(response.metrics.candidate_core_files, 4)
        self.assertEqual(response.metrics.total_files, 4)
        self.assertEqual(response.metrics.ignored_dirs, 0)
        self.assertEqual(response.metrics.selected_core_files, 2)
        self.assertEqual(response.metrics.read_files, 2)
        self.assertEqual(response.metrics.truncated_files, 2)
        self.assertEqual(response.metrics.final_context_chars, 20)
        self.assertGreater(response.metrics.raw_candidate_chars, response.metrics.final_context_chars)
        self.assertGreater(response.metrics.context_compression_ratio, 0)
        self.assertLess(response.metrics.context_compression_ratio, 1)
        self.assertEqual(response.metrics.mock_doc_count, 7)
        self.assertGreater(response.metrics.mock_doc_total_chars, 0)
        self.assertGreaterEqual(response.metrics.analysis_duration_ms, 0)
        self.assertEqual(response.metrics.agent_step_count, len(response.agent_steps))
        self.assertEqual(response.metrics.agent_success_step_count, 8)
        self.assertEqual(response.metrics.agent_failed_step_count, 0)
        self.assertEqual(response.metrics.agent_skipped_step_count, 1)
        self.assertEqual(response.metrics.tool_call_count, len(response.tool_logs))
        self.assertEqual(response.metrics.tool_success_count, 8)
        self.assertEqual(response.metrics.tool_failed_count, 0)
        self.assertGreaterEqual(response.metrics.avg_tool_duration_ms, 0)
        self.assertGreaterEqual(response.metrics.max_tool_duration_ms, response.metrics.avg_tool_duration_ms)
        self.assertGreaterEqual(response.metrics.total_tool_duration_ms, response.metrics.max_tool_duration_ms)
        self.assertTrue(all(step.duration_ms >= 0 for step in response.agent_steps))
        self.assertTrue(all(step.step_id for step in response.agent_steps))
        self.assertTrue(all(step.completed_at for step in response.agent_steps))
        self.assertIn("success", {step.status for step in response.agent_steps})
        self.assertIn("skipped", {step.status for step in response.agent_steps})
        self.assertIn("README.md", response.tool_logs[3].output["read_files"])
        select_log = next(log for log in response.tool_logs if log.tool_name == "select_core_files")
        self.assertIn("selected_files", select_log.output)
        self.assertTrue(select_log.related_files)
        context_log = next(log for log in response.tool_logs if log.tool_name == "build_analysis_context")
        self.assertIn("used_for_context", context_log.output)
        self.assertEqual(metrics_payload["operation"], "agent_analyze_mock")
        self.assertEqual(metrics_payload["total_files"], response.metrics.total_files)
        self.assertEqual(metrics_payload["ignored_dirs"], response.metrics.ignored_dirs)
        self.assertEqual(metrics_payload["mock_doc_count"], 7)
        self.assertEqual(metrics_payload["selected_core_files"], 2)
        self.assertTrue(metrics_payload["used_mock_ai"])
        self.assertEqual(metrics_payload["llm_call_count"], 0)
        self.assertEqual(metrics_payload["prompt_template_count"], 0)
        self.assertEqual(metrics_payload["generated_doc_count"], 7)
        self.assertGreater(metrics_payload["generated_doc_total_chars"], 0)
        self.assertEqual(metrics_payload["interview_question_count"], 3)
        self.assertEqual(metrics_payload["agent_step_count"], response.metrics.agent_step_count)
        self.assertEqual(metrics_payload["tool_call_count"], response.metrics.tool_call_count)
        self.assertEqual(metrics_payload["tool_success_count"], response.metrics.tool_success_count)
        self.assertEqual(metrics_payload["tool_failed_count"], response.metrics.tool_failed_count)
        self.assertEqual(metrics_payload["avg_tool_duration_ms"], response.metrics.avg_tool_duration_ms)
        self.assertEqual(len(history_payload), 1)
        self.assertEqual(history_payload[0]["repo_url"], "https://github.com/owner/repo")
        self.assertEqual(history_payload[0]["status"], "success")
        self.assertEqual(history_payload[0]["docs_dir"], response.docs_dir)
        self.assertEqual(history_payload[0]["core_files_count"], len(response.core_files))

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
            workflow.settings = SimpleNamespace(
                temp_repo_path=root / "temp_repos",
                generated_docs_path=root / "generated_docs",
                metrics_path=root / "data" / "metrics.jsonl",
                history_path=root / "data" / "history.json",
                mock_mode=True,
                openai_api_key=None,
                openai_model="test-model",
                max_file_tree_depth=4,
                max_file_tree_entries=100,
                max_basic_file_bytes=20_000,
                max_core_files=2,
                max_core_file_bytes=20,
            )
            workflow.clone_repository = lambda parsed_repo, temp_repo_path: repo_root
            try:
                workflow.run_codebase_analysis_job(
                    job_id=job.id,
                    repo_url="https://github.com/owner/repo",
                    job_service=job_service,
                    force_mock=True,
                )
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository

            events = job_service.get_events_after(job.id, 0)
            metrics_events = [event for event in events if event.type == "metrics_updated"]
            completed_event = next(event for event in events if event.type == "job_completed")

        self.assertGreaterEqual(len(metrics_events), 1)
        self.assertEqual(metrics_events[0].payload["metrics"]["total_files"], 3)
        self.assertEqual(metrics_events[0].payload["metrics"]["ignored_dirs"], 1)
        self.assertEqual(completed_event.payload["metrics"]["total_files"], 3)
        self.assertEqual(completed_event.payload["metrics"]["ignored_dirs"], 1)

    def test_analysis_falls_back_to_mock_when_api_key_is_missing(self) -> None:
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
                response = workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
            finally:
                workflow.settings = original_settings
                workflow.clone_repository = original_clone_repository
                workflow.generate_markdown_documents = original_generate_markdown_documents

        self.assertTrue(response.mock_mode)
        self.assertEqual(response.metrics.mock_doc_count, 7)

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

    def _raise_llm_error(self, **_: object) -> list[tuple[str, str, str]]:
        raise AppError(
            status_code=502,
            code="LLM_CALL_FAILED",
            message="AI 文档生成失败",
            detail="boom",
        )


if __name__ == "__main__":
    unittest.main()
