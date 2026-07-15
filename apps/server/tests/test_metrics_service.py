import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import repo as repo_api
from app.schemas.agent import CoreFileSummary, GeneratedDocument
from app.schemas.metrics import CoreFileSelectionMetrics
from app.services.llm_call_service import LLMCallRecord
from app.services.metrics_service import (
    build_mock_analysis_metrics,
)


pytestmark = pytest.mark.unit


def test_build_mock_analysis_metrics_uses_real_character_counts() -> None:
    metrics = build_mock_analysis_metrics(
        selection_metrics=CoreFileSelectionMetrics(
            candidate_core_files=4,
            raw_candidate_chars=100,
        ),
        core_files=[
            CoreFileSummary(
                path="README.md",
                file_type="Markdown",
                size=80,
                content_preview="a" * 30,
                truncated=True,
                reason="基础项目文件",
            ),
            CoreFileSummary(
                path="src/main.ts",
                file_type="TypeScript",
                size=20,
                content_preview="b" * 20,
                truncated=False,
                reason="入口文件",
            ),
        ],
        documents=[
            GeneratedDocument(title="项目概览", filename="01.md", path="generated_docs/demo/01.md", content="doc"),
            GeneratedDocument(title="技术栈", filename="02.md", path="generated_docs/demo/02.md", content="文档"),
        ],
        analysis_duration_ms=321,
    )

    assert metrics.candidate_core_files == 4
    assert metrics.selected_core_files == 2
    assert metrics.read_files == 2
    assert metrics.truncated_files == 1
    assert metrics.raw_candidate_chars == 100
    assert metrics.final_context_chars == 50
    assert metrics.context_compression_ratio == 0.5
    assert metrics.analysis_duration_ms == 321
    assert metrics.generated_doc_count == 2
    assert metrics.generated_doc_total_chars == 5
    assert metrics.generated_doc_total_words == 3
    assert metrics.interview_question_count == 0
    assert metrics.referenced_file_path_count == 0
    assert metrics.llm_call_count == 0
    assert metrics.llm_success_count == 0
    assert metrics.llm_failed_count == 0
    assert metrics.llm_total_duration_ms == 0
    assert metrics.used_mock_ai is True
    assert metrics.provider == ""
    assert metrics.model == ""
    assert metrics.prompt_template_count == 0


def test_build_mock_analysis_metrics_computes_llm_and_path_metrics() -> None:
    records = [
        LLMCallRecord(
            provider="openai",
            model="m",
            prompt_type="项目概览",
            duration_ms=10,
            status="success",
        ),
        LLMCallRecord(
            provider="openai",
            model="m",
            prompt_type="技术栈",
            duration_ms=5,
            status="failed",
            error_message="boom",
        ),
    ]
    documents = [
        GeneratedDocument(
            title="面试问题",
            filename="05-面试问题与回答.md",
            path="generated_docs/demo/05-面试问题与回答.md",
            content="## Q1：xxx\n## Q2：yyy",
        ),
        GeneratedDocument(
            title="技术栈",
            filename="02.md",
            path="generated_docs/demo/02.md",
            content="引用 `src/main.ts` 与 `README.md`。",
        ),
    ]

    metrics = build_mock_analysis_metrics(
        selection_metrics=CoreFileSelectionMetrics(candidate_core_files=0, raw_candidate_chars=0),
        core_files=[],
        documents=documents,
        analysis_duration_ms=100,
        used_mock_ai=False,
        provider="openai",
        model="m",
        prompt_template_count=7,
        llm_call_records=records,
    )

    assert metrics.interview_question_count == 2
    assert metrics.referenced_file_path_count >= 1
    assert metrics.llm_call_count == 2
    assert metrics.llm_success_count == 1
    assert metrics.llm_failed_count == 1
    assert metrics.llm_total_duration_ms == 15
    assert not metrics.used_mock_ai
    assert metrics.provider == "openai"
    assert metrics.model == "m"
    assert metrics.prompt_template_count == 7


def test_build_mock_analysis_metrics_computes_llm_and_path_metrics_duplicate() -> None:
    records = [
        LLMCallRecord(
            provider="openai",
            model="m",
            prompt_type="项目概览",
            duration_ms=10,
            status="success",
        ),
        LLMCallRecord(
            provider="openai",
            model="m",
            prompt_type="技术栈",
            duration_ms=5,
            status="failed",
            error_message="boom",
        ),
    ]
    documents = [
        GeneratedDocument(
            title="面试问题",
            filename="05-面试问题与回答.md",
            path="generated_docs/demo/05-面试问题与回答.md",
            content="## Q1：xxx\n## Q2：yyy",
        ),
        GeneratedDocument(
            title="技术栈",
            filename="02.md",
            path="generated_docs/demo/02.md",
            content="引用 `src/main.ts` 与 `README.md`。",
        ),
    ]

    metrics = build_mock_analysis_metrics(
        selection_metrics=CoreFileSelectionMetrics(candidate_core_files=0, raw_candidate_chars=0),
        core_files=[],
        documents=documents,
        analysis_duration_ms=100,
        used_mock_ai=False,
        provider="openai",
        model="m",
        prompt_template_count=7,
        llm_call_records=records,
    )

    assert metrics.interview_question_count == 2
    assert metrics.referenced_file_path_count >= 1
    assert metrics.llm_call_count == 2
    assert metrics.llm_success_count == 1
    assert metrics.llm_failed_count == 1
    assert metrics.llm_total_duration_ms == 15
    assert not metrics.used_mock_ai
    assert metrics.provider == "openai"
    assert metrics.model == "m"
    assert metrics.prompt_template_count == 7


def test_build_mock_analysis_metrics_sums_llm_token_usage() -> None:
    records = [
        LLMCallRecord(
            provider="openai",
            model="m",
            prompt_type="项目概览",
            duration_ms=10,
            status="success",
            input_tokens=12,
            output_tokens=8,
            total_tokens=20,
        ),
        LLMCallRecord(
            provider="openai",
            model="m",
            prompt_type="技术栈",
            duration_ms=5,
            status="success",
            input_tokens=3,
            output_tokens=2,
            total_tokens=5,
        ),
    ]

    metrics = build_mock_analysis_metrics(
        selection_metrics=CoreFileSelectionMetrics(candidate_core_files=0, raw_candidate_chars=0),
        core_files=[],
        documents=[],
        analysis_duration_ms=100,
        llm_call_records=records,
    )

    assert metrics.llm_input_tokens == 15
    assert metrics.llm_output_tokens == 10
    assert metrics.llm_total_tokens == 25


def test_build_mock_analysis_metrics_returns_zero_ratio_when_no_candidates() -> None:
    metrics = build_mock_analysis_metrics(
        selection_metrics=CoreFileSelectionMetrics(candidate_core_files=0, raw_candidate_chars=0),
        core_files=[],
        documents=[],
        analysis_duration_ms=0,
    )

    assert metrics.context_compression_ratio == 0


def test_parse_repo_does_not_create_metrics_file() -> None:
    from app.schemas.repo import RepoRequest
    with tempfile.TemporaryDirectory() as tmp:
        metrics_file = Path(tmp) / "metrics.jsonl"
        original_settings = repo_api.settings
        repo_api.settings = SimpleNamespace()
        try:
            response = repo_api.parse_repo(RepoRequest(repo_url="https://github.com/owner/repo"))
        finally:
            repo_api.settings = original_settings

        assert not metrics_file.exists()

    assert response.owner == "owner"


def test_scan_repo_does_not_create_metrics_file_without_network() -> None:
    from app.schemas.repo import RepoRequest
    from app.schemas.repo import BasicFileSummary, FileTreeNode
    with tempfile.TemporaryDirectory() as tmp:
        temp_root = Path(tmp)
        metrics_file = temp_root / "metrics.jsonl"
        tree = [
            FileTreeNode(
                name="src",
                path="src",
                type="directory",
                children=[FileTreeNode(name="main.ts", path="src/main.ts", type="file")],
            )
        ]
        basic_files = [
            BasicFileSummary(
                path="README.md",
                file_type="markdown",
                size=128,
                content_preview="# Demo",
                truncated=False,
            )
        ]

        original_settings = repo_api.settings
        original_clone = repo_api.clone_repository
        original_build_tree = repo_api.build_file_tree
        original_read_basic_files = repo_api.read_basic_files
        repo_api.settings = SimpleNamespace(
            temp_repo_path=temp_root,
            max_file_tree_depth=4,
            max_file_tree_entries=100,
            max_basic_file_bytes=20_000,
        )
        repo_api.clone_repository = lambda parsed_repo, temp_repo_path: temp_root
        repo_api.build_file_tree = lambda root, *, max_depth, max_entries: tree
        repo_api.read_basic_files = lambda root, *, max_bytes: basic_files
        try:
            response = repo_api.scan_repo(RepoRequest(repo_url="https://github.com/owner/repo"))
        finally:
            repo_api.settings = original_settings
            repo_api.clone_repository = original_clone
            repo_api.build_file_tree = original_build_tree
            repo_api.read_basic_files = original_read_basic_files

        assert not metrics_file.exists()

    assert response.owner == "owner"
