from pathlib import Path
from typing import Any

import pytest
from langgraph.runtime import Runtime

import app.agent_graph.nodes.build_analysis_context as build_context_node_module
import app.agent_graph.nodes.build_context_quality_report as quality_node_module
import app.agent_graph.nodes.clone_repo as clone_repo_module
import app.agent_graph.nodes.select_core_files as select_node_module
from app.agent_graph.context import AnalysisRuntimeContext
from app.agent_graph.graph_builder import build_analysis_graph
from app.agent_graph.nodes.build_analysis_context import build_analysis_context
from app.agent_graph.nodes.build_context_quality_report import build_context_quality_report
from app.agent_graph.nodes.fetch_github_mcp_context import fetch_github_mcp_context
from app.agent_graph.nodes.select_core_files import select_core_files
from app.agent_graph.runner import run_analysis_graph
from app.core.errors import AppError
from app.mcp.schemas import McpTool, McpToolCallResult
from app.schemas.agent import ContextQualityReport, CoreFileSummary
from app.schemas.metrics import CoreFileSelectionMetrics
from app.schemas.repo import BasicFileSummary, RepoParseResponse
from app.services.file_selector_service import select_core_files_with_metrics
from app.services.mcp_tool_service import McpToolService
from app.services.metrics_service import build_context_quality_report as build_quality_report_service

pytestmark = pytest.mark.unit


def _create_sample_repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "README.md").write_text("# Sample\n", encoding="utf-8")
    (root / "src" / "main.py").write_text("from .service import run\nrun()\n", encoding="utf-8")
    (root / "src" / "service.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")


def _parsed_repo() -> RepoParseResponse:
    return RepoParseResponse(
        owner="owner",
        repo="repo",
        repo_url="https://github.com/owner/repo",
    )


def _core_file() -> CoreFileSummary:
    return CoreFileSummary(
        path="src/main.py",
        file_type="Python",
        size=10,
        content_preview="print('ok')",
        truncated=False,
        reason="entry",
    )


class FakeGithubMcpClient:
    def list_tools(self, server_name: str) -> list[McpTool]:
        return []

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> McpToolCallResult:
        payloads = {
            "list_issues": [{"number": 1, "title": "Fix bug", "state": "open"}],
            "list_pull_requests": [{"number": 2, "title": "Add feature", "state": "open"}],
            "list_commits": [{"sha": "abc", "commit": {"message": "Initial commit"}}],
        }
        content = payloads[tool_name]
        return McpToolCallResult(content=content, summary=f"Returned {len(content)} items")


def _mcp_service() -> McpToolService:
    return McpToolService(
        client=FakeGithubMcpClient(),
        server_name="github",
        allowed_tools={"list_issues", "list_pull_requests", "list_commits"},
    )


def test_phase2_graph_completes_deterministic_context_pipeline(monkeypatch, tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: tmp_path)

    result = run_analysis_graph("owner/repo", job_id="job-2")

    assert result["core_files"]
    assert result["context_quality_report"].selected_file_count == len(result["core_files"])
    assert "## 仓库信息" in result["analysis_context"]
    assert "## 核心文件摘要" in result["analysis_context"]
    assert result["github_mcp_context"] == ""
    assert [step.key for step in result["agent_steps"]] == [
        "parse_repo_url",
        "clone_repository",
        "build_file_tree",
        "read_basic_files",
        "select_core_files",
        "build_analysis_context",
        "fetch_github_mcp_context",
    ]
    assert [step.status for step in result["agent_steps"]] == [
        "success",
        "success",
        "success",
        "success",
        "success",
        "success",
        "skipped",
    ]
    assert [log.tool_name for log in result["tool_logs"]] == [
        "parse_github_repo_url",
        "clone_repository",
        "build_file_tree",
        "read_basic_files",
        "select_core_files",
        "build_analysis_context",
        "fetch_github_mcp_context",
    ]
    assert "documents" not in result
    assert "result_evaluation" not in result


def test_select_node_delegates_to_existing_service(monkeypatch, tmp_path: Path) -> None:
    core_files = [_core_file()]
    selection_metrics = CoreFileSelectionMetrics(candidate_core_files=1, raw_candidate_chars=11)
    calls: list[tuple[Path, int, int]] = []

    def fake_select(root: Path, *, max_files: int, max_bytes: int):
        calls.append((root, max_files, max_bytes))
        return core_files, selection_metrics

    monkeypatch.setattr(select_node_module, "select_core_files_with_metrics", fake_select)

    update = select_core_files({"local_path": str(tmp_path)})

    assert update["core_files"] == core_files
    assert update["selection_metrics"] == selection_metrics
    assert calls and calls[0][0] == tmp_path
    assert update["agent_steps"][-1].key == "select_core_files"
    assert update["tool_logs"][-1].tool_name == "select_core_files"


def test_quality_report_node_delegates_without_creating_audit_records(monkeypatch) -> None:
    expected = ContextQualityReport(
        candidate_file_count=1,
        selected_file_count=1,
        omitted_candidate_count=0,
        context_char_count=11,
        raw_candidate_chars=11,
        compression_ratio=1,
        truncated_selected_file_count=0,
        budget_limit_reached=False,
        selected_files=["src/main.py"],
        directory_coverage=[],
        selection_reasons=[],
        omitted_candidates=[],
    )
    calls: list[tuple[CoreFileSelectionMetrics, list[CoreFileSummary]]] = []

    def fake_report(*, selection_metrics, core_files):
        calls.append((selection_metrics, core_files))
        return expected

    monkeypatch.setattr(quality_node_module, "create_context_quality_report", fake_report)
    state = {
        "selection_metrics": CoreFileSelectionMetrics(candidate_core_files=1),
        "core_files": [_core_file()],
        "agent_steps": [],
        "tool_logs": [],
    }

    update = build_context_quality_report(state)

    assert update == {"context_quality_report": expected}
    assert calls == [(state["selection_metrics"], state["core_files"])]


def test_build_context_node_delegates_to_existing_prompt_service(monkeypatch) -> None:
    basic_files = [
        BasicFileSummary(
            path="README.md",
            file_type="markdown",
            size=9,
            content_preview="# Sample\n",
            truncated=False,
        )
    ]

    calls: list[tuple[RepoParseResponse, list[BasicFileSummary], list[CoreFileSummary]]] = []

    def fake_build_context(*, parsed_repo, basic_files, core_files):
        calls.append((parsed_repo, basic_files, core_files))
        return "assembled context"

    monkeypatch.setattr(build_context_node_module, "create_analysis_context", fake_build_context)

    update = build_analysis_context(
        {
            "parsed_repo": _parsed_repo(),
            "basic_files": basic_files,
            "core_files": [_core_file()],
        }
    )

    assert update["analysis_context"] == "assembled context"
    assert calls == [(_parsed_repo(), basic_files, [_core_file()])]
    assert update["agent_steps"][-1].key == "build_analysis_context"
    assert update["tool_logs"][-1].tool_name == "build_analysis_context"


def test_fetch_mcp_context_uses_runtime_dependency_and_merges_context() -> None:
    runtime = Runtime[AnalysisRuntimeContext](context={"mcp_service": _mcp_service()})

    update = fetch_github_mcp_context(
        {
            "parsed_repo": _parsed_repo(),
            "analysis_context": "base context",
        },
        runtime,
    )

    assert "Recent open issues" in update["github_mcp_context"]
    assert update["analysis_context"].startswith("base context\n\n## GitHub 协作上下文")
    assert [log.tool_name for log in update["tool_logs"]] == [
        "mcp.github.list_issues",
        "mcp.github.list_pull_requests",
        "mcp.github.list_commits",
        "fetch_github_mcp_context",
    ]
    assert update["agent_steps"][-1].status == "success"
    assert "mcp_service" not in update


def test_graph_stage_adapter_preserves_app_error_audit(monkeypatch, tmp_path: Path) -> None:
    original_error = AppError(
        status_code=500,
        code="CORE_FILE_SELECTION_FAILED",
        message="selection failed",
        detail="broken repository",
    )

    def fail_selection(root: Path, *, max_files: int, max_bytes: int):
        raise original_error

    monkeypatch.setattr(select_node_module, "select_core_files_with_metrics", fail_selection)

    with pytest.raises(AppError) as exc_info:
        select_core_files({"local_path": str(tmp_path)})

    assert exc_info.value is original_error
    assert exc_info.value.agent_steps[-1].key == "select_core_files"
    assert exc_info.value.agent_steps[-1].status == "failed"
    assert exc_info.value.tool_logs[-1].tool_name == "select_core_files"
    assert exc_info.value.tool_logs[-1].status == "failed"
    assert exc_info.value.tool_logs[-1].output == {"error_code": "CORE_FILE_SELECTION_FAILED"}


def test_graph_outputs_match_existing_services_without_mcp(monkeypatch, tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: tmp_path)

    result = run_analysis_graph("owner/repo")
    expected_files, expected_metrics = select_core_files_with_metrics(tmp_path)
    expected_report = build_quality_report_service(
        selection_metrics=expected_metrics,
        core_files=expected_files,
    )

    assert result["core_files"] == expected_files
    assert result["selection_metrics"] == expected_metrics
    assert result["context_quality_report"] == expected_report
    assert result["github_mcp_context"] == ""


def test_compiled_graph_without_runtime_context_treats_mcp_as_unconfigured(monkeypatch, tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: tmp_path)

    result = build_analysis_graph().invoke({"repo_url": "owner/repo"})

    assert result["github_mcp_context"] == ""
    assert result["agent_steps"][-1].key == "fetch_github_mcp_context"
    assert result["agent_steps"][-1].status == "skipped"
