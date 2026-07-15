import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.agent import workflow
from app.db.models import AnalysisJobRow
from app.mcp.schemas import McpTool, McpToolCallResult
from app.services import history_service
from app.services.analysis_job_repository import InMemoryAnalysisJobRepository
from app.services.analysis_job_service import AnalysisJobService
from app.services.mcp_tool_service import McpToolService


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def isolate_history_database(db_session_factory, monkeypatch):
    monkeypatch.setattr(history_service, "SessionLocal", db_session_factory)


# ── 辅助函数 ─────────────────────────────────────────────────────

def _create_repo(root: Path) -> Path:
    repo_root = root / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("demo readme", encoding="utf-8")
    (repo_root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (repo_root / "src").mkdir()
    (repo_root / "src" / "main.ts").write_text("console.log('demo')", encoding="utf-8")
    return repo_root


def _fail_if_called(**_: object) -> list[tuple[str, str, str]]:
    raise AssertionError("generate_markdown_documents should not be called")


def _fake_markdown_documents(*, recorder=None, **_: object) -> list[tuple[str, str, str]]:
    if recorder is not None:
        recorder.record(prompt_type="真实文档", duration_ms=5, status="success")
    return [("真实文档", "01-项目概览.md", "# Real AI Doc\n\n引用 `README.md`。")]


def _fake_markdown_documents_expect_github_context(*, context: str, recorder=None, **_: object) -> list[tuple[str, str, str]]:
    assert "## GitHub 协作上下文" in context
    assert "#7 Improve onboarding docs" in context
    if recorder is not None:
        recorder.record(prompt_type="真实文档", duration_ms=5, status="success")
    return [("真实文档", "01-项目概览.md", "# Real AI Doc\n\n## Context\n\n引用 `README.md`。")]


def _raise_llm_error(**_: object) -> list[tuple[str, str, str]]:
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


# ── 测试 ─────────────────────────────────────────────────────────

def test_real_analysis_response_contains_metrics_without_network(db_session_factory) -> None:
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
        original_generate_markdown_documents = workflow.generate_markdown_documents
        workflow.settings = SimpleNamespace(
            temp_repo_path=root / "temp_repos",
            generated_docs_path=generated_docs_path,
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
        workflow.generate_markdown_documents = _fake_markdown_documents
        try:
            response = workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
        finally:
            workflow.settings = original_settings
            workflow.clone_repository = original_clone_repository
            workflow.generate_markdown_documents = original_generate_markdown_documents

        assert not metrics_path.exists()
        history_records = history_service.list_history_records(
            history_file=history_path,
            session_factory=db_session_factory,
        )
        with db_session_factory() as session:
            history_row = session.get(AnalysisJobRow, history_records[0].id)

    assert response.metrics.candidate_core_files == 2
    assert response.metrics.total_files == 4
    assert response.metrics.ignored_dirs == 0
    assert response.metrics.selected_core_files == 2
    assert response.metrics.read_files == 2
    assert response.metrics.truncated_files == 2
    assert response.metrics.final_context_chars == 20
    assert response.context_quality_report.candidate_file_count == 2
    assert response.context_quality_report.selected_file_count == 2
    assert response.context_quality_report.omitted_candidate_count == 0
    assert response.context_quality_report.context_char_count == 20
    assert response.context_quality_report.raw_candidate_chars == response.metrics.raw_candidate_chars
    assert response.context_quality_report.compression_ratio == response.metrics.context_compression_ratio
    assert not response.context_quality_report.budget_limit_reached
    assert response.context_quality_report.selected_files == ["src/main.ts", "app/main.py"]
    assert {item.directory for item in response.context_quality_report.directory_coverage} == {"app", "src"}
    assert response.context_quality_report.omitted_candidates == []
    assert response.metrics.raw_candidate_chars > response.metrics.final_context_chars
    assert response.metrics.context_compression_ratio > 0
    assert response.metrics.context_compression_ratio < 1
    assert response.metrics.generated_doc_count == 1
    assert response.metrics.generated_doc_total_chars > 0
    assert response.metrics.analysis_duration_ms >= 0
    assert response.metrics.agent_step_count == len(response.agent_steps)
    assert response.metrics.agent_success_step_count == 9
    assert response.metrics.agent_failed_step_count == 0
    assert response.metrics.agent_skipped_step_count == 1
    assert response.metrics.tool_call_count == len(response.tool_logs)
    assert response.metrics.tool_success_count == 9
    assert response.metrics.tool_failed_count == 0
    assert all(log.tool_provider == "builtin" for log in response.tool_logs)
    assert all(log.permission for log in response.tool_logs)
    llm_tool_log = next(log for log in response.tool_logs if log.tool_name == "llm_service.generate_markdown_documents")
    assert llm_tool_log.permission == "llm"
    assert "document_count" in llm_tool_log.input_schema["properties"]
    assert response.metrics.avg_tool_duration_ms >= 0
    assert response.metrics.max_tool_duration_ms >= response.metrics.avg_tool_duration_ms
    assert response.metrics.total_tool_duration_ms >= response.metrics.max_tool_duration_ms
    assert all(step.duration_ms >= 0 for step in response.agent_steps)
    assert all(step.step_id for step in response.agent_steps)
    assert all(step.completed_at for step in response.agent_steps)
    assert "success" in {step.status for step in response.agent_steps}
    assert "skipped" in {step.status for step in response.agent_steps}
    mcp_skipped_log = next(log for log in response.tool_logs if log.tool_name == "fetch_github_mcp_context")
    assert mcp_skipped_log.status == "skipped"
    assert mcp_skipped_log.permission == "read"
    assert response.result_evaluation.document_count == 1
    assert response.result_evaluation.valid_reference_count == 1
    assert response.result_evaluation.invalid_reference_count == 0
    assert response.result_evaluation.textcitation_score == 1
    assert response.result_evaluation.coverage_score == 0.25
    assert response.result_evaluation.usefulness_score < 1
    evaluation_log = next(log for log in response.tool_logs if log.tool_name == "evaluate_generated_documents")
    assert evaluation_log.permission == "read"
    assert evaluation_log.output["textcitation_score"] == 1
    assert "README.md" in response.tool_logs[3].output["read_files"]
    select_log = next(log for log in response.tool_logs if log.tool_name == "select_core_files")
    assert "selected_files" in select_log.output
    assert select_log.related_files
    context_log = next(log for log in response.tool_logs if log.tool_name == "build_analysis_context")
    assert "used_for_context" in context_log.output
    assert len(history_records) == 1
    assert history_records[0].repo_url == "https://github.com/owner/repo"
    assert history_records[0].status == "success"
    assert history_records[0].docs_dir == response.docs_dir
    assert history_records[0].core_files_count == len(response.core_files)
    assert history_row.metrics_json["total_files"] == response.metrics.total_files
    assert history_row.metrics_json["tool_call_count"] == response.metrics.tool_call_count
    assert not history_path.exists()


def test_job_workflow_emits_metrics_updated_with_scan_counts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_root = _create_repo(root)
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
        workflow.generate_markdown_documents = _fake_markdown_documents
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

    assert len(metrics_events) >= 1
    assert metrics_events[0].payload["metrics"]["total_files"] == 3
    assert metrics_events[0].payload["metrics"]["ignored_dirs"] == 1
    assert repo_loaded_event.payload["context_quality_report"]["selected_file_count"] == 1
    assert repo_loaded_event.payload["context_quality_report"]["omitted_candidate_count"] == 0
    assert completed_event.payload["metrics"]["total_files"] == 3
    assert completed_event.payload["metrics"]["ignored_dirs"] == 1
    assert completed_event.payload["result"]["result_evaluation"]["document_count"] == 7
    assert completed_event.payload["result"]["result_evaluation"]["textcitation_score"] == 1


def test_workflow_merges_github_mcp_context_before_llm_generation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_root = _create_repo(root)
        original_settings = workflow.settings
        original_clone_repository = workflow.clone_repository
        original_generate_markdown_documents = workflow.generate_markdown_documents
        original_github_mcp_service = workflow._github_mcp_service
        workflow.settings = SimpleNamespace(
            temp_repo_path=root / "temp_repos",
            generated_docs_path=root / "generated_docs",
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
        workflow.generate_markdown_documents = _fake_markdown_documents_expect_github_context
        workflow._github_mcp_service = lambda: McpToolService(
            client=_FakeGithubMcpClient(),
            server_name="github",
            allowed_tools={"list_issues", "list_pull_requests", "list_commits"},
        )
        try:
            response = workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
        finally:
            workflow.settings = original_settings
            workflow.clone_repository = original_clone_repository
            workflow.generate_markdown_documents = original_generate_markdown_documents
            workflow._github_mcp_service = original_github_mcp_service

    assert any(log.tool_name == "fetch_github_mcp_context" for log in response.tool_logs)
    assert any(log.tool_name == "mcp.github.list_issues" for log in response.tool_logs)
    assert response.metrics.agent_skipped_step_count == 0


def test_analysis_requires_llm_api_key() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_root = _create_repo(root)
        generated_docs_path = root / "generated_docs"

        original_settings = workflow.settings
        original_clone_repository = workflow.clone_repository
        original_generate_markdown_documents = workflow.generate_markdown_documents
        workflow.settings = SimpleNamespace(
            temp_repo_path=root / "temp_repos",
            generated_docs_path=generated_docs_path,
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
        workflow.generate_markdown_documents = _fail_if_called
        try:
            with pytest.raises(AppError) as raised:
                workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
        finally:
            workflow.settings = original_settings
            workflow.clone_repository = original_clone_repository
            workflow.generate_markdown_documents = original_generate_markdown_documents

    assert raised.value.code == "LLM_API_KEY_MISSING"
    assert raised.value.status_code == 400


def test_analysis_uses_llm_service_when_api_key_is_configured() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_root = _create_repo(root)
        generated_docs_path = root / "generated_docs"
        metrics_path = root / "data" / "metrics.jsonl"

        original_settings = workflow.settings
        original_clone_repository = workflow.clone_repository
        original_generate_markdown_documents = workflow.generate_markdown_documents
        workflow.settings = SimpleNamespace(
            temp_repo_path=root / "temp_repos",
            generated_docs_path=generated_docs_path,
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
        workflow.generate_markdown_documents = _fake_markdown_documents
        try:
            response = workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
        finally:
            workflow.settings = original_settings
            workflow.clone_repository = original_clone_repository
            workflow.generate_markdown_documents = original_generate_markdown_documents

        assert not metrics_path.exists()

    assert not response.mock_mode
    assert response.documents[0].content == "# Real AI Doc\n\n引用 `README.md`。"
    assert not response.metrics.used_mock_ai
    assert response.metrics.provider == "deepseek"
    assert response.metrics.model == "deepseek-v4-flash"
    assert response.metrics.llm_call_count == 1
    assert response.metrics.llm_success_count == 1
    assert response.metrics.llm_total_duration_ms == 5
    assert response.metrics.prompt_template_count == 7
    assert response.metrics.generated_doc_count == 1
    assert response.metrics.referenced_file_path_count == 1
    assert response.metrics.interview_question_count == 0


def test_analysis_returns_structured_error_when_llm_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo_root = _create_repo(root)

        original_settings = workflow.settings
        original_clone_repository = workflow.clone_repository
        original_generate_markdown_documents = workflow.generate_markdown_documents
        workflow.settings = SimpleNamespace(
            temp_repo_path=root / "temp_repos",
            generated_docs_path=root / "generated_docs",
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
        workflow.generate_markdown_documents = _raise_llm_error
        try:
            with pytest.raises(AppError) as raised:
                workflow.run_codebase_analysis_workflow("https://github.com/owner/repo")
        finally:
            workflow.settings = original_settings
            workflow.clone_repository = original_clone_repository
            workflow.generate_markdown_documents = original_generate_markdown_documents

    assert raised.value.code == "LLM_CALL_FAILED"
    assert raised.value.status_code == 502
    failed_steps = [step for step in raised.value.agent_steps if step.status == "failed"]
    assert failed_steps[-1].key == "generate_real_ai_documents"
    assert failed_steps[-1].error_message == "AI 文档生成失败"
    assert raised.value.tool_logs[-1].status == "failed"
    assert raised.value.tool_logs[-1].error_message == "boom"
