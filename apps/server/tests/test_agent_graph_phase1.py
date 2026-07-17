from pathlib import Path

import pytest

import app.agent_graph.nodes.clone_repo as clone_repo_module
import app.agent_graph.nodes.parse_repo as parse_repo_module
import app.agent_graph.nodes.scan_repo as scan_repo_module
from app.agent_graph.nodes.clone_repo import clone_repo
from app.agent_graph.nodes.parse_repo import parse_repo
from app.agent_graph.nodes.scan_repo import scan_repo
from app.agent_graph.runner import run_analysis_graph
from app.core.errors import AppError
from app.schemas.repo import BasicFileSummary, FileTreeNode, RepoParseResponse
from app.services.file_tree_service import build_file_tree, read_basic_files
from app.services.repo_parser import parse_github_repo_url

pytestmark = pytest.mark.unit


def _create_sample_repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "README.md").write_text("# Sample\n", encoding="utf-8")
    (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")


def test_valid_github_url_completes_three_node_graph(monkeypatch, tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: tmp_path)

    result = run_analysis_graph("https://github.com/owner/repo", job_id="job-1")

    assert result["job_id"] == "job-1"
    assert result["parsed_repo"].owner == "owner"
    assert result["parsed_repo"].repo == "repo"
    assert result["local_path"] == str(tmp_path)
    assert {node.name for node in result["file_tree"]} == {"README.md", "src"}
    assert [file.path for file in result["basic_files"]] == ["README.md"]


def test_invalid_url_fails_in_parse_node_before_clone(monkeypatch) -> None:
    def fail_if_called(parsed_repo, temp_root):
        raise AssertionError("clone_repository should not run after parse failure")

    monkeypatch.setattr(clone_repo_module, "clone_repository", fail_if_called)

    with pytest.raises(AppError) as exc_info:
        run_analysis_graph("https://example.com/owner/repo")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_GITHUB_URL"


def test_clone_error_preserves_original_app_error(monkeypatch) -> None:
    clone_error = AppError(
        status_code=502,
        code="REPO_CLONE_FAILED",
        message="clone failed",
        detail="network unavailable",
    )

    def raise_clone_error(parsed_repo, temp_root):
        raise clone_error

    monkeypatch.setattr(clone_repo_module, "clone_repository", raise_clone_error)

    with pytest.raises(AppError) as exc_info:
        run_analysis_graph("https://github.com/owner/repo")

    assert exc_info.value is clone_error
    assert exc_info.value.code == "REPO_CLONE_FAILED"
    assert exc_info.value.detail == "network unavailable"


def test_scan_node_returns_file_tree_and_basic_files(tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)

    update = scan_repo({"local_path": str(tmp_path)})

    assert {node.name for node in update["file_tree"]} == {"README.md", "src"}
    assert [file.path for file in update["basic_files"]] == ["README.md"]


def test_nodes_delegate_to_existing_services(monkeypatch, tmp_path: Path) -> None:
    parsed_repo = RepoParseResponse(
        owner="owner",
        repo="repo",
        repo_url="https://github.com/owner/repo",
    )
    file_tree = [FileTreeNode(name="README.md", path="README.md", type="file")]
    basic_files = [
        BasicFileSummary(
            path="README.md",
            file_type="markdown",
            size=8,
            content_preview="# Sample",
            truncated=False,
        )
    ]
    calls: list[str] = []

    def fake_parse(repo_url: str) -> RepoParseResponse:
        calls.append(f"parse:{repo_url}")
        return parsed_repo

    def fake_clone(value: RepoParseResponse, temp_root: Path) -> Path:
        calls.append(f"clone:{value.repo_url}")
        return tmp_path

    def fake_tree(root: Path, *, max_depth: int, max_entries: int) -> list[FileTreeNode]:
        calls.append(f"tree:{root}")
        return file_tree

    def fake_basic(root: Path, *, max_bytes: int) -> list[BasicFileSummary]:
        calls.append(f"basic:{root}")
        return basic_files

    monkeypatch.setattr(parse_repo_module, "parse_github_repo_url", fake_parse)
    monkeypatch.setattr(clone_repo_module, "clone_repository", fake_clone)
    monkeypatch.setattr(scan_repo_module, "build_file_tree", fake_tree)
    monkeypatch.setattr(scan_repo_module, "read_basic_files", fake_basic)

    parse_update = parse_repo({"repo_url": parsed_repo.repo_url})
    clone_update = clone_repo({"parsed_repo": parsed_repo})
    scan_update = scan_repo({"local_path": str(tmp_path)})

    assert parse_update["parsed_repo"] == parsed_repo
    assert clone_update["local_path"] == str(tmp_path)
    assert scan_update["file_tree"] == file_tree
    assert scan_update["basic_files"] == basic_files
    assert parse_update["agent_steps"][-1].key == "parse_repo_url"
    assert clone_update["tool_logs"][-1].tool_name == "clone_repository"
    assert [step.key for step in scan_update["agent_steps"]] == ["build_file_tree", "read_basic_files"]
    assert calls == [
        f"parse:{parsed_repo.repo_url}",
        f"clone:{parsed_repo.repo_url}",
        f"tree:{tmp_path}",
        f"basic:{tmp_path}",
    ]


def test_graph_result_matches_existing_services_for_same_repository(monkeypatch, tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: tmp_path)

    result = run_analysis_graph("owner/repo")
    expected_parsed_repo = parse_github_repo_url("owner/repo")
    expected_tree = build_file_tree(tmp_path)
    expected_basic_files = read_basic_files(tmp_path)

    assert result["parsed_repo"] == expected_parsed_repo
    assert result["local_path"] == str(tmp_path)
    assert result["file_tree"] == expected_tree
    assert result["basic_files"] == expected_basic_files
