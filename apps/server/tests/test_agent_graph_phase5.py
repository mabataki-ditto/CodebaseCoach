from collections import Counter
import sqlite3
from pathlib import Path

import pytest

import app.agent_graph.nodes.clone_repo as clone_repo_module
import app.agent_graph.nodes.evaluate_documents as evaluate_node_module
import app.agent_graph.nodes.generate_document as generate_document_module
import app.agent_graph.runner as runner_module
from app.agent.prompts import REAL_DOCUMENT_PROMPTS
from app.agent_graph.graph_builder import build_analysis_graph
from app.agent_graph.runner import _validate_resume_state, run_analysis_graph
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.agent import GeneratedResultEvaluation
from app.schemas.repo import RepoParseResponse
from app.services.graph_run_service import GraphRunService

pytestmark = pytest.mark.unit


def _create_sample_repository(root: Path) -> Path:
    repo = root / "repository"
    (repo / "src").mkdir(parents=True)
    (repo / "README.md").write_text("# Sample\n", encoding="utf-8")
    (repo / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    return repo


def _install_generation_that_fails_once_on_document_six(monkeypatch) -> Counter[str]:
    calls: Counter[str] = Counter()

    def fake_generate_document(*, document_prompt, context, api_key, model, base_url, recorder):
        calls[document_prompt.filename] += 1
        if document_prompt.filename.startswith("06") and calls[document_prompt.filename] == 1:
            raise AppError(
                status_code=502,
                code="LLM_CALL_FAILED",
                message="generation failed",
                detail="simulated document 6 failure",
            )
        recorder.record(
            prompt_type=document_prompt.title,
            duration_ms=1,
            status="success",
            total_tokens=1,
        )
        return document_prompt.title, document_prompt.filename, f"# {document_prompt.title}"

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", fake_generate_document)
    return calls


def _passing_quality_result() -> GeneratedResultEvaluation:
    return GeneratedResultEvaluation(
        document_count=7,
        evaluated_document_count=7,
        textcitation_score=1,
        coverage_score=1,
        hallucination_risk=0,
        usefulness_score=1,
        valid_reference_count=7,
        invalid_reference_count=0,
        referenced_context_file_count=1,
        context_file_count=1,
        interview_question_count=8,
        interview_question_target=8,
        document_evaluations=[],
        issues=[],
    )


def test_phase5_checkpointer_is_opt_in(tmp_path: Path) -> None:
    default_graph = build_analysis_graph(include_document_generation=True)
    with GraphRunService(tmp_path / "checkpoints.sqlite3") as graph_runs:
        persistent_graph = build_analysis_graph(
            include_document_generation=True,
            checkpointer=graph_runs.checkpointer,
        )

        assert default_graph.checkpointer is None
        assert persistent_graph.checkpointer is graph_runs.checkpointer
        assert "generate_documents" in default_graph.get_graph().nodes
        assert "generate_documents" not in persistent_graph.get_graph().nodes
        assert "generate_document_01" in persistent_graph.get_graph().nodes
        assert "merge_documents" in persistent_graph.get_graph().nodes


def test_phase5_persistent_run_requires_thread_identity(tmp_path: Path) -> None:
    with GraphRunService(tmp_path / "checkpoints.sqlite3") as graph_runs:
        with pytest.raises(AppError) as raised:
            run_analysis_graph("owner/repo", graph_run_service=graph_runs)

    assert raised.value.code == "GRAPH_THREAD_ID_MISSING"


def test_phase5_resume_requires_existing_checkpoint(tmp_path: Path) -> None:
    with GraphRunService(tmp_path / "checkpoints.sqlite3") as graph_runs:
        with pytest.raises(AppError) as raised:
            run_analysis_graph(
                "owner/repo",
                job_id="missing-job",
                graph_run_service=graph_runs,
                resume=True,
            )

    assert raised.value.code == "GRAPH_CHECKPOINT_NOT_FOUND"


def test_phase5_resume_requires_graph_run_service() -> None:
    with pytest.raises(AppError) as raised:
        run_analysis_graph("owner/repo", job_id="job", resume=True)

    assert raised.value.code == "GRAPH_CHECKPOINTER_REQUIRED"


def test_phase5_recovery_does_not_repeat_successful_parallel_documents(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = _create_sample_repository(tmp_path)
    clone_calls = 0

    def fake_clone(parsed_repo, temp_root):
        nonlocal clone_calls
        clone_calls += 1
        return repo

    monkeypatch.setattr(clone_repo_module, "clone_repository", fake_clone)
    calls = _install_generation_that_fails_once_on_document_six(monkeypatch)
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    secret = "phase-5-runtime-secret"
    phase5_settings = get_settings().model_copy(update={"llm_max_workers": 7})
    monkeypatch.setattr(runner_module, "get_settings", lambda: phase5_settings)

    with GraphRunService(checkpoint_path) as graph_runs:
        with pytest.raises(AppError) as raised:
            run_analysis_graph(
                "owner/repo",
                job_id="recover-job",
                graph_run_service=graph_runs,
                include_document_generation=True,
                llm_api_key=secret,
                llm_model="phase-5-model",
            )

    assert raised.value.code == "LLM_CALL_FAILED"

    # Reopen the SQLite store to prove recovery is durable across service instances.
    with GraphRunService(checkpoint_path) as graph_runs:
        result = run_analysis_graph(
            "owner/repo",
            job_id="recover-job",
            graph_run_service=graph_runs,
            include_document_generation=True,
            resume=True,
            llm_api_key=secret,
            llm_model="phase-5-model",
        )

    expected_filenames = [prompt.filename for prompt in REAL_DOCUMENT_PROMPTS]
    assert [filename for _, filename, _ in result["documents"]] == expected_filenames
    assert clone_calls == 1
    assert calls[expected_filenames[5]] == 2
    assert all(calls[filename] == 1 for filename in expected_filenames[:5]), calls
    assert calls[expected_filenames[6]] == 1
    checkpoint_bytes = b"".join(path.read_bytes() for path in tmp_path.glob("checkpoints.sqlite3*"))
    assert secret.encode() not in checkpoint_bytes


def test_phase5_fresh_run_rejects_existing_thread_and_delete_allows_reset(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: repo)
    checkpoint_path = tmp_path / "checkpoints.sqlite3"

    with GraphRunService(checkpoint_path) as graph_runs:
        first = run_analysis_graph("owner/repo", job_id="same-job", graph_run_service=graph_runs)
        with pytest.raises(AppError) as raised:
            run_analysis_graph("owner/repo", job_id="same-job", graph_run_service=graph_runs)

        assert first["parsed_repo"].repo == "repo"
        assert raised.value.code == "GRAPH_THREAD_EXISTS"

        graph_runs.delete_thread("same-job")
        restarted = run_analysis_graph("owner/repo", job_id="same-job", graph_run_service=graph_runs)

    assert restarted["parsed_repo"].repo == "repo"


def test_phase5_persistent_quality_graph_keeps_phase4_output_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: repo)
    calls: Counter[str] = Counter()

    def fake_generate_document(*, document_prompt, context, api_key, model, base_url, recorder):
        calls[document_prompt.filename] += 1
        recorder.record(
            prompt_type=document_prompt.title,
            duration_ms=1,
            status="success",
            total_tokens=1,
        )
        return document_prompt.title, document_prompt.filename, f"# {document_prompt.title}"

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", fake_generate_document)
    monkeypatch.setattr(
        evaluate_node_module,
        "evaluate_generated_documents",
        lambda **kwargs: _passing_quality_result(),
    )

    with GraphRunService(tmp_path / "checkpoints.sqlite3") as graph_runs:
        result = run_analysis_graph(
            "owner/repo",
            job_id="quality-job",
            graph_run_service=graph_runs,
            include_quality_loop=True,
            llm_api_key="runtime-only-secret",
            llm_model="phase-5-model",
        )

    expected_filenames = [prompt.filename for prompt in REAL_DOCUMENT_PROMPTS]
    assert [filename for _, filename, _ in result["documents"]] == expected_filenames
    assert result["quality_passed"] is True
    assert all(calls[filename] == 1 for filename in expected_filenames)
    assert "document_results" not in result


def test_phase5_checkpoint_store_is_separate_from_business_database(tmp_path: Path) -> None:
    settings = get_settings()
    assert settings.graph_checkpoint_path != Path(
        settings.resolved_database_url.removeprefix("sqlite:///")
    )

    checkpoint_path = tmp_path / "runtime" / "checkpoints.sqlite3"
    with GraphRunService(checkpoint_path) as graph_runs:
        assert graph_runs.has_checkpoint("probe") is False

    assert checkpoint_path.exists()
    with sqlite3.connect(checkpoint_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "checkpoints" in tables
    assert "analysis_jobs" not in tables


def test_phase5_resume_rejects_missing_process_local_repository(tmp_path: Path) -> None:
    with pytest.raises(AppError) as raised:
        _validate_resume_state(
            {
                "repo_url": "owner/repo",
                "local_path": str(tmp_path / "missing-repository"),
            },
            repo_url="owner/repo",
        )

    assert raised.value.code == "GRAPH_LOCAL_PATH_MISSING"


def test_phase5_resume_compares_canonical_repository_urls(tmp_path: Path) -> None:
    _validate_resume_state(
        {
            "repo_url": "owner/repo",
            "parsed_repo": RepoParseResponse(
                owner="owner",
                repo="repo",
                repo_url="https://github.com/owner/repo",
            ),
            "local_path": str(tmp_path),
        },
        repo_url="https://github.com/owner/repo.git",
    )

    with pytest.raises(AppError) as raised:
        _validate_resume_state(
            {
                "repo_url": "owner/repo",
                "parsed_repo": RepoParseResponse(
                    owner="owner",
                    repo="repo",
                    repo_url="https://github.com/owner/repo",
                ),
                "local_path": str(tmp_path),
            },
            repo_url="other/project",
        )

    assert raised.value.code == "GRAPH_REPO_MISMATCH"
