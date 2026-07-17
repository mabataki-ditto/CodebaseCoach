from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.agent_graph.nodes.clone_repo as clone_repo_module
import app.agent_graph.nodes.evaluate_documents as evaluate_node_module
import app.agent_graph.nodes.generate_document as generate_document_module
import app.services.analysis_execution_service as execution_module
from app.agent.prompts import REAL_DOCUMENT_PROMPTS
from app.agent_graph.runner import run_analysis_graph
from app.api import agent as agent_api
from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.schemas.agent import GeneratedDocumentEvaluation, GeneratedResultEvaluation
from app.schemas.repo import RepoParseResponse
from app.services.analysis_execution_service import (
    AnalysisExecutionService,
    AnalysisJobCancelled,
    langgraph_thread_id,
)
from app.services.analysis_job_repository import InMemoryAnalysisJobRepository
from app.services.analysis_job_service import AnalysisJobService
from app.services.langgraph_event_adapter import LangGraphEventAdapter
from app.services.graph_run_service import GraphRunService


pytestmark = pytest.mark.unit


def _job_service() -> AnalysisJobService:
    repository = InMemoryAnalysisJobRepository()
    return AnalysisJobService(
        job_repository=repository,
        event_repository=repository,
        artifact_repository=repository,
    )


def _sample_repository(root: Path) -> Path:
    repository = root / "repository"
    (repository / "src").mkdir(parents=True)
    (repository / "README.md").write_text("# Sample\n", encoding="utf-8")
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


def _install_graph_fakes(monkeypatch, repository: Path) -> Counter[str]:
    calls: Counter[str] = Counter()
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: repository)

    def generate(*, document_prompt, context, api_key, model, base_url, recorder):
        calls[document_prompt.filename] += 1
        recorder.record(
            prompt_type=document_prompt.title,
            duration_ms=1,
            status="success",
            total_tokens=1,
        )
        return document_prompt.title, document_prompt.filename, f"# {document_prompt.title}\n\n## Details\n\n`README.md`"

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", generate)
    monkeypatch.setattr(
        evaluate_node_module,
        "evaluate_generated_documents",
        lambda **kwargs: _passing_evaluation(),
    )
    return calls


def _langgraph_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        analysis_engine="langgraph",
        llm_api_key="phase-6-key",
        graph_checkpoint_file=str(tmp_path / "checkpoints.sqlite3"),
        generated_docs_dir=str(tmp_path / "generated_docs"),
        history_file=str(tmp_path / "history.json"),
        database_url=f"sqlite:///{(tmp_path / 'business.sqlite3').as_posix()}",
        mcp_config_file=None,
    )


def test_phase6_analysis_engine_defaults_to_legacy_and_rejects_unknown_values() -> None:
    assert Settings(_env_file=None).analysis_engine == "legacy"

    with pytest.raises(ValidationError):
        Settings(_env_file=None, analysis_engine="automatic")


def test_phase6_execution_service_keeps_legacy_sync_and_job_calls_unchanged() -> None:
    calls: list[tuple] = []
    expected_response = object()
    job_service = _job_service()
    job = job_service.create_job("owner/repo")
    service = AnalysisExecutionService(
        settings_provider=lambda: SimpleNamespace(analysis_engine="legacy"),
        legacy_sync_runner=lambda repo_url: calls.append(("sync", repo_url)) or expected_response,
        legacy_job_runner=lambda **kwargs: calls.append(("job", kwargs)),
    )

    assert service.run_sync("owner/repo") is expected_response
    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)

    assert calls == [
        ("sync", "owner/repo"),
        (
            "job",
            {"job_id": job.id, "repo_url": "owner/repo", "job_service": job_service},
        ),
    ]


def test_phase6_thread_id_is_stable_and_internal() -> None:
    assert langgraph_thread_id("job-123") == "analysis:job-123"


def test_phase6_event_adapter_preserves_sse_names_and_deduplicates_raw_event_ids() -> None:
    job_service = _job_service()
    job = job_service.create_job("owner/repo")
    adapter = LangGraphEventAdapter(job_id=job.id, job_service=job_service)
    raw_event = {
        "event_id": "parse-started",
        "type": "stage_started",
        "payload": {
            "key": "parse_repo_url",
            "title": "Parse GitHub URL",
            "description": "Run workflow stage",
        },
    }

    adapter.handle_custom_event(raw_event)
    adapter.handle_custom_event(raw_event)

    events = job_service.get_events_after(job.id, 0)
    assert [event.type for event in events] == ["stage_started"]
    assert events[0].payload == raw_event["payload"]
    assert all(not event.type.startswith("langgraph") for event in events)


def test_phase6_cancellation_uses_existing_job_cancel_flag() -> None:
    job_service = _job_service()
    job = job_service.create_job("owner/repo")
    job_service.request_cancel(job.id)

    with pytest.raises(AnalysisJobCancelled):
        AnalysisExecutionService.raise_if_cancelled(job.id, job_service)


def test_phase6_formal_async_job_uses_graph_and_preserves_sse_and_persistence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = _sample_repository(tmp_path)
    calls = _install_graph_fakes(monkeypatch, repository)
    settings = _langgraph_settings(tmp_path)
    job_service = _job_service()
    job = job_service.create_job("owner/repo")
    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        mcp_service_factory=lambda: None,
        api_key_provider=lambda: "phase-6-key",
    )

    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)

    snapshot = job_service.get_snapshot(job.id)
    event_types = [event.type for event in snapshot.events]
    assert snapshot.job.status == "success"
    assert snapshot.result is not None
    assert len(snapshot.documents) == len(REAL_DOCUMENT_PROMPTS)
    assert [document.filename for document in snapshot.documents] == [
        prompt.filename for prompt in REAL_DOCUMENT_PROMPTS
    ]
    assert event_types[0] == "job_started"
    assert event_types.count("job_completed") == 1
    assert event_types.count("job_failed") == 0
    assert event_types.count("job_cancelled") == 0
    assert event_types.count("document_generated") == len(REAL_DOCUMENT_PROMPTS)
    assert event_types.count("metrics_updated") == len(REAL_DOCUMENT_PROMPTS) + 2
    assert set(event_types) <= {
        "job_started",
        "stage_started",
        "stage_completed",
        "stage_failed",
        "metrics_updated",
        "document_generated",
        "job_completed",
        "job_failed",
        "job_cancelled",
    }
    assert all(calls[prompt.filename] == 1 for prompt in REAL_DOCUMENT_PROMPTS)
    assert all(
        (
            settings.generated_docs_path
            / Path(document.path).relative_to(settings.generated_docs_path.name)
        ).is_file()
        for document in snapshot.documents
    )
    with GraphRunService(settings.graph_checkpoint_path) as graph_runs:
        assert not graph_runs.has_checkpoint(langgraph_thread_id(job.id))


def test_phase6_formal_sync_api_keeps_response_contract_and_hides_graph_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = _sample_repository(tmp_path)
    _install_graph_fakes(monkeypatch, repository)
    settings = _langgraph_settings(tmp_path)
    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        mcp_service_factory=lambda: None,
        api_key_provider=lambda: "phase-6-key",
    )
    monkeypatch.setattr(execution_module, "_record_history", lambda **kwargs: None)
    monkeypatch.setattr(agent_api, "analysis_execution_service", service)

    response = TestClient(create_app()).post(
        "/api/agent/analyze",
        json={"repo_url": "owner/repo"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["owner"] == "owner"
    assert payload["repo"] == "repo"
    assert len(payload["documents"]) == len(REAL_DOCUMENT_PROMPTS)
    assert "thread_id" not in payload
    assert "local_path" not in payload
    assert "analysis_context" not in payload


def test_phase6_formal_async_api_and_sse_use_langgraph_execution_service(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = _sample_repository(tmp_path)
    _install_graph_fakes(monkeypatch, repository)
    settings = _langgraph_settings(tmp_path)
    job_service = _job_service()
    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        mcp_service_factory=lambda: None,
        api_key_provider=lambda: "phase-6-key",
    )

    class ImmediateThread:
        def __init__(self, *, target, kwargs, daemon=True):
            self._target = target
            self._kwargs = kwargs

        def start(self):
            self._target(**self._kwargs)

    monkeypatch.setattr(agent_api, "analysis_execution_service", service)
    monkeypatch.setattr(agent_api, "analysis_job_service", job_service)
    monkeypatch.setattr(agent_api, "require_llm_configuration", lambda: None)
    monkeypatch.setattr(agent_api, "Thread", ImmediateThread)
    client = TestClient(create_app())

    created = client.post("/api/agent/analyze/jobs", json={"repo_url": "owner/repo"})
    assert created.status_code == 200
    job_id = created.json()["job_id"]
    snapshot = client.get(f"/api/agent/analyze/jobs/{job_id}")
    events = client.get(f"/api/agent/analyze/jobs/{job_id}/events")

    assert snapshot.status_code == 200
    assert snapshot.json()["job"]["status"] == "success"
    assert events.status_code == 200
    assert "event: job_started" in events.text
    assert "event: document_generated" in events.text
    assert events.text.count("event: job_completed") == 1
    assert "langgraph" not in events.text.lower()


def test_phase6_failed_document_job_resumes_same_checkpoint_without_repeating_successes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = _sample_repository(tmp_path)
    calls = _install_graph_fakes(monkeypatch, repository)
    original_generate = generate_document_module.generate_markdown_document
    failed_filename = REAL_DOCUMENT_PROMPTS[3].filename

    def fail_document_four_once(**kwargs):
        prompt = kwargs["document_prompt"]
        if prompt.filename == failed_filename and calls[prompt.filename] == 0:
            calls[prompt.filename] += 1
            raise AppError(
                status_code=502,
                code="LLM_CALL_FAILED",
                message="generation failed",
            )
        return original_generate(**kwargs)

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", fail_document_four_once)
    settings = _langgraph_settings(tmp_path)
    job_service = _job_service()
    job = job_service.create_job("owner/repo")
    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        mcp_service_factory=lambda: None,
        api_key_provider=lambda: "phase-6-key",
    )

    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)
    assert job_service.get_job(job.id).status == "failed"
    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)

    snapshot = job_service.get_snapshot(job.id)
    assert snapshot.job.status == "success"
    assert snapshot.job.error_message is None
    assert len(snapshot.documents) == len(REAL_DOCUMENT_PROMPTS)
    assert calls[failed_filename] == 2
    assert all(
        calls[prompt.filename] == 1
        for prompt in REAL_DOCUMENT_PROMPTS
        if prompt.filename != failed_filename
    )
    assert [event.type for event in snapshot.events].count("job_completed") == 1
    monkeypatch.setattr(agent_api, "analysis_job_service", job_service)
    replayed_events = TestClient(create_app()).get(
        f"/api/agent/analyze/jobs/{job.id}/events"
    )
    assert replayed_events.status_code == 200
    assert "event: job_completed" in replayed_events.text
    assert "event: job_failed" not in replayed_events.text


def test_phase6_quality_loop_retries_only_document_with_attributable_issues(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = _sample_repository(tmp_path)
    calls = _install_graph_fakes(monkeypatch, repository)
    target = REAL_DOCUMENT_PROMPTS[2]
    evaluations = 0

    def evaluate(**kwargs):
        nonlocal evaluations
        evaluations += 1
        if evaluations > 1:
            return _passing_evaluation()
        issue = f"{target.filename}: contains placeholder text: TODO."
        return GeneratedResultEvaluation(
            **{
                **_passing_evaluation().model_dump(),
                "textcitation_score": 0.6,
                "document_evaluations": [
                    GeneratedDocumentEvaluation(
                        filename=target.filename,
                        title=target.title,
                        has_title=True,
                        char_count=10,
                        referenced_file_paths=[],
                        valid_referenced_file_paths=[],
                        invalid_referenced_file_paths=[],
                        placeholder_hits=["TODO"],
                        issues=[issue],
                    )
                ],
                "issues": [issue],
            }
        )

    monkeypatch.setattr(evaluate_node_module, "evaluate_generated_documents", evaluate)

    result = run_analysis_graph(
        "owner/repo",
        include_quality_loop=True,
        selective_quality_retry=True,
        llm_api_key="phase-6-key",
        llm_model="phase-6-model",
    )

    assert result["quality_passed"] is True
    assert result["quality_retry_count"] == 1
    assert calls[target.filename] == 2
    assert all(
        calls[prompt.filename] == 1
        for prompt in REAL_DOCUMENT_PROMPTS
        if prompt.filename != target.filename
    )


def test_phase6_terminal_event_failure_keeps_checkpoint_and_business_writes_idempotent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = _sample_repository(tmp_path)
    calls = _install_graph_fakes(monkeypatch, repository)
    storage = InMemoryAnalysisJobRepository()

    class FailCompletedOnceJobService(AnalysisJobService):
        fail_completed = True

        def append_event(self, job_id, event_type, payload=None):
            if event_type == "job_completed" and self.fail_completed:
                self.fail_completed = False
                raise RuntimeError("simulated terminal event write failure")
            return super().append_event(job_id, event_type, payload)

    job_service = FailCompletedOnceJobService(
        job_repository=storage,
        event_repository=storage,
        artifact_repository=storage,
    )
    job = job_service.create_job("owner/repo")
    settings = _langgraph_settings(tmp_path)
    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        mcp_service_factory=lambda: None,
        api_key_provider=lambda: "phase-6-key",
    )

    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)
    assert job_service.get_job(job.id).status == "failed"
    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)

    snapshot = job_service.get_snapshot(job.id)
    event_types = [event.type for event in snapshot.events]
    assert snapshot.job.status == "success"
    assert event_types.count("document_generated") == len(REAL_DOCUMENT_PROMPTS)
    assert event_types.count("metrics_updated") == len(REAL_DOCUMENT_PROMPTS) + 2
    assert event_types.count("job_completed") == 1
    assert all(calls[prompt.filename] == 1 for prompt in REAL_DOCUMENT_PROMPTS)


def test_phase6_cancelled_graph_job_never_enters_success(monkeypatch, tmp_path: Path) -> None:
    settings = _langgraph_settings(tmp_path)
    job_service = _job_service()
    job = job_service.create_job("owner/repo")

    def cancel_during_graph(repo_url, **kwargs):
        kwargs["on_state_update"](
            {
                "parsed_repo": RepoParseResponse(
                    owner="owner",
                    repo="repo",
                    repo_url="https://github.com/owner/repo",
                )
            }
        )
        kwargs["on_graph_event"](
            {
                "type": "document_ready",
                "payload": {
                    "index": 0,
                    "title": "Overview",
                    "filename": "01-overview.md",
                    "content": "# Overview",
                },
            }
        )
        job_service.request_cancel(job.id)
        kwargs["cancel_check"]()
        raise AssertionError("cancel check must stop execution")

    service = AnalysisExecutionService(
        settings_provider=lambda: settings,
        graph_runner=cancel_during_graph,
        mcp_service_factory=lambda: None,
        api_key_provider=lambda: "phase-6-key",
    )

    service.run_job(job_id=job.id, repo_url=job.repo_url, job_service=job_service)

    snapshot = job_service.get_snapshot(job.id)
    event_types = [event.type for event in snapshot.events]
    assert snapshot.job.status == "cancelled"
    assert [document.filename for document in snapshot.documents] == ["01-overview.md"]
    assert event_types.count("document_generated") == 1
    assert event_types.count("job_cancelled") == 1
    assert "job_completed" not in event_types
