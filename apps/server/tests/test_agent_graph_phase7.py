from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path
import shutil

import pytest
from fastapi.testclient import TestClient

from app.api import agent as agent_api
import app.agent_graph.nodes.clone_repo as clone_repo_module
import app.agent_graph.nodes.evaluate_documents as evaluate_node_module
import app.agent_graph.nodes.generate_document as generate_document_module
from app.agent.prompts import REAL_DOCUMENT_PROMPTS
from app.agent_graph.nodes.prepare_repository_recovery import prepare_repository_recovery
from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.db.repositories import SqlAnalysisJobRepository
from app.schemas.agent import GeneratedResultEvaluation
from app.services.analysis_execution_service import AnalysisExecutionService
from app.services.analysis_job_repository import InMemoryAnalysisJobRepository
from app.services.analysis_job_service import AnalysisJobService


pytestmark = pytest.mark.unit


def _job_service() -> AnalysisJobService:
    repository = InMemoryAnalysisJobRepository()
    return AnalysisJobService(
        job_repository=repository,
        event_repository=repository,
        artifact_repository=repository,
    )


class _FakeGraphRuns:
    def __init__(self, *, has_checkpoint: bool = True, state: dict | None = None) -> None:
        self._has_checkpoint = has_checkpoint
        self._state = state or {}

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def has_checkpoint(self, thread_id: str) -> bool:
        return self._has_checkpoint

    def get_checkpoint_state(self, thread_id: str) -> dict:
        return self._state


def _execution_service(tmp_path: Path, graph_runs: _FakeGraphRuns) -> AnalysisExecutionService:
    settings = Settings(
        _env_file=None,
        analysis_engine="langgraph",
        graph_checkpoint_file=str(tmp_path / "checkpoints.sqlite3"),
    )
    return AnalysisExecutionService(
        settings_provider=lambda: settings,
        graph_run_service_factory=lambda _: graph_runs,
    )


def _failed_langgraph_job(job_service: AnalysisJobService):
    job = job_service.create_job("https://github.com/owner/repo")
    job_service.update_status(job.id, "failed", error_message="boom", mock_mode=False)
    job_service.put_artifact(job.id, "execution_metadata", {"engine": "langgraph"})
    return job


def _sample_repository(root: Path, name: str) -> Path:
    repository = root / name
    (repository / "src").mkdir(parents=True)
    (repository / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    (repository / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    return repository


def _passing_evaluation() -> GeneratedResultEvaluation:
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


def test_phase7_resume_status_allows_failed_langgraph_checkpoint(tmp_path: Path) -> None:
    job_service = _job_service()
    job = _failed_langgraph_job(job_service)
    repository = tmp_path / "repo"
    repository.mkdir()
    service = _execution_service(tmp_path, _FakeGraphRuns(state={"local_path": str(repository)}))

    status = service.get_resume_status(job.id, job_service)

    assert status.job_id == job.id
    assert status.can_resume is True
    assert status.job_status == "failed"
    assert status.engine == "langgraph"
    assert status.recovery_mode == "checkpoint"
    assert status.reason is None
    assert "thread_id" not in status.model_dump()
    assert "local_path" not in status.model_dump()


def test_phase7_resume_status_rebuilds_when_local_repository_is_missing(tmp_path: Path) -> None:
    job_service = _job_service()
    job = _failed_langgraph_job(job_service)
    service = _execution_service(
        tmp_path,
        _FakeGraphRuns(
            state={
                "local_path": str(tmp_path / "missing"),
                "repository_commit_sha": "commit-a",
            }
        ),
    )

    status = service.get_resume_status(job.id, job_service)

    assert status.can_resume is True
    assert status.recovery_mode == "rebuild_repository"


def test_phase7_resume_status_uses_full_restart_for_legacy_checkpoint_without_sha(tmp_path: Path) -> None:
    job_service = _job_service()
    job = _failed_langgraph_job(job_service)
    service = _execution_service(
        tmp_path,
        _FakeGraphRuns(state={"local_path": str(tmp_path / "missing")}),
    )

    status = service.get_resume_status(job.id, job_service)

    assert status.can_resume is True
    assert status.recovery_mode == "full_restart"


@pytest.mark.parametrize("status", ["queued", "running", "success", "cancelled"])
def test_phase7_resume_status_rejects_non_failed_jobs(tmp_path: Path, status: str) -> None:
    job_service = _job_service()
    job = job_service.create_job("https://github.com/owner/repo")
    job_service.update_status(job.id, status)
    job_service.put_artifact(job.id, "execution_metadata", {"engine": "langgraph"})
    service = _execution_service(tmp_path, _FakeGraphRuns())

    result = service.get_resume_status(job.id, job_service)

    assert result.can_resume is False
    assert result.recovery_mode is None
    assert result.reason


def test_phase7_resume_status_rejects_legacy_missing_metadata_and_missing_checkpoint(tmp_path: Path) -> None:
    for metadata, has_checkpoint in [({"engine": "legacy"}, True), (None, True), ({"engine": "langgraph"}, False)]:
        job_service = _job_service()
        job = job_service.create_job("https://github.com/owner/repo")
        job_service.update_status(job.id, "failed")
        if metadata is not None:
            job_service.put_artifact(job.id, "execution_metadata", metadata)
        service = _execution_service(tmp_path, _FakeGraphRuns(has_checkpoint=has_checkpoint))

        result = service.get_resume_status(job.id, job_service)

        assert result.can_resume is False
        assert result.reason


def test_phase7_resume_status_rejects_when_current_engine_is_legacy(tmp_path: Path) -> None:
    job_service = _job_service()
    job = _failed_langgraph_job(job_service)
    settings = Settings(_env_file=None, analysis_engine="legacy")
    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        graph_run_service_factory=lambda _: _FakeGraphRuns(),
    )

    result = service.get_resume_status(job.id, job_service)

    assert result.can_resume is False
    assert "LangGraph" in (result.reason or "")


def test_phase7_only_one_concurrent_resume_claim_succeeds(tmp_path: Path) -> None:
    job_service = _job_service()
    job = _failed_langgraph_job(job_service)
    repository = tmp_path / "repo"
    repository.mkdir()
    service = _execution_service(tmp_path, _FakeGraphRuns(state={"local_path": str(repository)}))

    def claim():
        try:
            return service.resume_job(job.id, job_service)
        except AppError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))

    successes = [result for result in results if not isinstance(result, AppError)]
    failures = [result for result in results if isinstance(result, AppError)]
    assert len(successes) == 1
    assert successes[0].job_id == job.id
    assert successes[0].status == "running"
    assert successes[0].resumed is True
    assert len(failures) == 1
    assert failures[0].status_code == 409
    assert job_service.get_job(job.id).status == "running"
    assert job_service.get_job(job.id).cancel_requested is False


def test_phase7_sql_repository_transition_is_conditional(db_session_factory) -> None:
    repository = SqlAnalysisJobRepository(db_session_factory)
    job_service = AnalysisJobService(
        job_repository=repository,
        event_repository=repository,
        artifact_repository=repository,
    )
    job = job_service.create_job("https://github.com/owner/repo")
    job_service.update_status(job.id, "failed")

    first = repository.try_transition_status(
        job.id,
        expected_statuses={"failed"},
        new_status="running",
    )
    second = repository.try_transition_status(
        job.id,
        expected_statuses={"failed"},
        new_status="running",
    )

    assert first is not None
    assert first.status == "running"
    assert second is None


def test_phase7_formal_resume_api_uses_same_job_and_hides_internal_state(monkeypatch, tmp_path: Path) -> None:
    job_service = _job_service()
    job = _failed_langgraph_job(job_service)
    repository = tmp_path / "repo"
    repository.mkdir()
    service = _execution_service(tmp_path, _FakeGraphRuns(state={"local_path": str(repository)}))
    started: list[dict] = []

    class _Thread:
        def __init__(self, *, target, kwargs, daemon):
            started.append({"target": target, "kwargs": kwargs, "daemon": daemon})

        def start(self) -> None:
            return None

    monkeypatch.setattr(agent_api, "analysis_job_service", job_service)
    monkeypatch.setattr(agent_api, "analysis_execution_service", service)
    monkeypatch.setattr(agent_api, "Thread", _Thread)

    with TestClient(create_app()) as client:
        status_response = client.get(f"/api/agent/analyze/jobs/{job.id}/resume-status")
        resume_response = client.post(f"/api/agent/analyze/jobs/{job.id}/resume")

    assert status_response.status_code == 200
    assert status_response.json()["recovery_mode"] == "checkpoint"
    assert resume_response.status_code == 200
    assert resume_response.json() == {
        "job_id": job.id,
        "status": "running",
        "resumed": True,
        "recovery_mode": "checkpoint",
    }
    assert set(status_response.json()) == {
        "job_id",
        "can_resume",
        "job_status",
        "engine",
        "recovery_mode",
        "reason",
    }
    assert len(started) == 1
    assert started[0]["kwargs"]["job_id"] == job.id
    assert started[0]["kwargs"]["repo_url"] == job.repo_url


def test_phase7_resume_api_reverts_to_failed_when_thread_start_fails(monkeypatch, tmp_path: Path) -> None:
    job_service = _job_service()
    job = _failed_langgraph_job(job_service)
    repository = tmp_path / "repo"
    repository.mkdir()
    service = _execution_service(tmp_path, _FakeGraphRuns(state={"local_path": str(repository)}))

    class _BrokenThread:
        def __init__(self, **kwargs):
            pass

        def start(self) -> None:
            raise RuntimeError("thread unavailable")

    monkeypatch.setattr(agent_api, "analysis_job_service", job_service)
    monkeypatch.setattr(agent_api, "analysis_execution_service", service)
    monkeypatch.setattr(agent_api, "Thread", _BrokenThread)

    with TestClient(create_app()) as client:
        response = client.post(f"/api/agent/analyze/jobs/{job.id}/resume")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ANALYSIS_JOB_RESUME_START_FAILED"
    assert job_service.get_job(job.id).status == "failed"


def test_phase7_recovery_preparation_keeps_only_same_commit_results() -> None:
    kept = prepare_repository_recovery(
        {"repository_commit_sha": "same", "recovery_source_commit_sha": "same"}
    )
    restarted = prepare_repository_recovery(
        {"repository_commit_sha": "new", "recovery_source_commit_sha": "old"}
    )

    assert kept == {"recovery_mode": "rebuild_repository"}
    assert restarted["recovery_mode"] == "full_restart"


@pytest.mark.parametrize(
    ("old_sha", "new_sha", "expected_mode", "expected_other_calls"),
    [
        ("commit-a", "commit-a", "rebuild_repository", 1),
        ("commit-a", "commit-b", "full_restart", 2),
        ("", "commit-b", "full_restart", 2),
    ],
)
def test_phase7_missing_local_path_rebuilds_safely(
    monkeypatch,
    tmp_path: Path,
    old_sha: str,
    new_sha: str,
    expected_mode: str,
    expected_other_calls: int,
) -> None:
    first_repository = _sample_repository(tmp_path, "first")
    rebuilt_repository = _sample_repository(tmp_path, "rebuilt")
    clone_calls = 0

    def clone_repository(*args):
        nonlocal clone_calls
        clone_calls += 1
        return first_repository if clone_calls == 1 else rebuilt_repository

    monkeypatch.setattr(clone_repo_module, "clone_repository", clone_repository)
    monkeypatch.setattr(
        clone_repo_module,
        "get_repository_commit_sha",
        lambda path: old_sha if path == first_repository else new_sha,
    )
    calls: Counter[str] = Counter()
    failed_filename = REAL_DOCUMENT_PROMPTS[3].filename

    def generate(*, document_prompt, recorder, **kwargs):
        calls[document_prompt.filename] += 1
        if document_prompt.filename == failed_filename and calls[document_prompt.filename] == 1:
            raise AppError(status_code=502, code="LLM_CALL_FAILED", message="generation failed")
        recorder.record(
            prompt_type=document_prompt.title,
            duration_ms=1,
            status="success",
            total_tokens=1,
        )
        return (
            document_prompt.title,
            document_prompt.filename,
            f"# {document_prompt.title}\n\n`README.md`",
        )

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", generate)
    monkeypatch.setattr(
        evaluate_node_module,
        "evaluate_generated_documents",
        lambda **kwargs: _passing_evaluation(),
    )
    settings = Settings(
        _env_file=None,
        analysis_engine="langgraph",
        llm_api_key="phase-7-key",
        graph_checkpoint_file=str(tmp_path / "checkpoints.sqlite3"),
        generated_docs_dir=str(tmp_path / "generated_docs"),
        history_file=str(tmp_path / "history.json"),
        database_url=f"sqlite:///{(tmp_path / 'business.sqlite3').as_posix()}",
        mcp_config_file=None,
    )
    job_service = _job_service()
    job = job_service.create_job("owner/repo")
    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        mcp_service_factory=lambda: None,
        api_key_provider=lambda: "phase-7-key",
    )

    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)
    assert job_service.get_job(job.id).status == "failed"
    shutil.rmtree(first_repository)
    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)

    snapshot = job_service.get_snapshot(job.id)
    metadata = job_service.get_artifact_payload(job.id, "execution_metadata")
    assert snapshot.job.status == "success"
    assert len(snapshot.documents) == len(REAL_DOCUMENT_PROMPTS)
    assert clone_calls == 2
    assert metadata["recovery_mode"] == expected_mode
    assert metadata["repository_commit_sha"] == new_sha
    assert calls[failed_filename] == 2
    assert all(
        calls[prompt.filename] == expected_other_calls
        for prompt in REAL_DOCUMENT_PROMPTS
        if prompt.filename != failed_filename
    )
    assert [event.type for event in snapshot.events].count("job_completed") == 1
    assert [event.type for event in snapshot.events].count("document_generated") == 7
    assert [event.sequence for event in snapshot.events] == list(
        range(1, len(snapshot.events) + 1)
    )
    assert sum(
        event.type == "metrics_updated" and event.payload.get("phase") == "completed"
        for event in snapshot.events
    ) == 1
    if expected_mode == "full_restart":
        readme = next(item for item in snapshot.basic_files if item.path == "README.md")
        assert "rebuilt" in readme.content_preview


def test_phase7_recovery_can_fail_again_without_losing_checkpoint(monkeypatch, tmp_path: Path) -> None:
    repository = _sample_repository(tmp_path, "repository")
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda *args: repository)
    monkeypatch.setattr(clone_repo_module, "get_repository_commit_sha", lambda path: "commit-a")
    calls: Counter[str] = Counter()
    failed_filename = REAL_DOCUMENT_PROMPTS[3].filename

    def generate(*, document_prompt, recorder, **kwargs):
        calls[document_prompt.filename] += 1
        if document_prompt.filename == failed_filename and calls[document_prompt.filename] <= 2:
            raise AppError(status_code=502, code="LLM_CALL_FAILED", message="generation failed")
        recorder.record(
            prompt_type=document_prompt.title,
            duration_ms=1,
            status="success",
            total_tokens=1,
        )
        return document_prompt.title, document_prompt.filename, f"# {document_prompt.title}\n\n`README.md`"

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", generate)
    monkeypatch.setattr(
        evaluate_node_module,
        "evaluate_generated_documents",
        lambda **kwargs: _passing_evaluation(),
    )
    settings = Settings(
        _env_file=None,
        analysis_engine="langgraph",
        llm_api_key="phase-7-key",
        graph_checkpoint_file=str(tmp_path / "checkpoints.sqlite3"),
        generated_docs_dir=str(tmp_path / "generated_docs"),
        database_url=f"sqlite:///{(tmp_path / 'business.sqlite3').as_posix()}",
        mcp_config_file=None,
    )
    job_service = _job_service()
    job = job_service.create_job("owner/repo")
    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        mcp_service_factory=lambda: None,
        api_key_provider=lambda: "phase-7-key",
    )

    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)
    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)

    assert job_service.get_job(job.id).status == "failed"
    assert service.get_resume_status(job.id, job_service).can_resume is True
    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)
    assert job_service.get_job(job.id).status == "success"
    assert calls[failed_filename] == 3
    assert all(
        calls[prompt.filename] == 1
        for prompt in REAL_DOCUMENT_PROMPTS
        if prompt.filename != failed_filename
    )
