import pytest
from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.main import create_app
from app.schemas.agent import GeneratedDocument
from app.services.analysis_job_repository import InMemoryAnalysisJobRepository
from app.services.analysis_job_service import AnalysisJobService


pytestmark = pytest.mark.unit


@pytest.fixture
def job_service():
    """创建内存级别的 AnalysisJobService，用于测试。"""
    repository = InMemoryAnalysisJobRepository()
    return AnalysisJobService(
        job_repository=repository,
        event_repository=repository,
        artifact_repository=repository,
    )


# ── Service 层测试 ──────────────────────────────────────────────

def test_create_job_and_append_events_with_sequence(job_service: AnalysisJobService) -> None:
    job = job_service.create_job("https://github.com/owner/repo")

    first = job_service.append_event(job.id, "job_started", {"repo_url": job.repo_url})
    second = job_service.append_event(job.id, "stage_started", {"stage": "clone"})
    events = job_service.get_events_after(job.id, 0)

    assert job.status == "queued"
    assert [event.sequence for event in events] == [1, 2]
    assert first.sequence == 1
    assert second.sequence == 2


def test_update_status_and_cancel_request(job_service: AnalysisJobService) -> None:
    job = job_service.create_job("https://github.com/owner/repo")

    running = job_service.update_status(job.id, "running", owner="owner", repo="repo", mock_mode=False)
    cancelled_requested = job_service.request_cancel(job.id)

    assert running.status == "running"
    assert running.owner == "owner"
    assert running.repo == "repo"
    assert not running.mock_mode
    assert cancelled_requested.cancel_requested
    assert job_service.is_cancel_requested(job.id)


def test_snapshot_returns_documents_artifact(job_service: AnalysisJobService) -> None:
    job = job_service.create_job("https://github.com/owner/repo")
    document = GeneratedDocument(title="项目概览", filename="01.md", path="generated_docs/demo/01.md", content="# Demo")

    job_service.put_artifact(job.id, "documents", [document.model_dump()])
    snapshot = job_service.get_snapshot(job.id)

    assert len(snapshot.documents) == 1
    assert snapshot.documents[0].filename == "01.md"


# ── API 层测试 ──────────────────────────────────────────────────

def test_create_job_and_stream_events(job_service: AnalysisJobService) -> None:
    original_runner = agent_api.run_codebase_analysis_job
    original_thread = agent_api.Thread
    original_require_llm_configuration = agent_api.require_llm_configuration
    original_service = agent_api.analysis_job_service

    class ImmediateThread:
        def __init__(self, *, target, kwargs, daemon=True):
            self._target = target
            self._kwargs = kwargs

        def start(self):
            self._target(**self._kwargs)

    def fake_runner(*, job_id, repo_url, job_service):
        job_service.update_status(job_id, "running")
        job_service.append_event(job_id, "job_started", {"repo_url": repo_url, "mock_mode": False})
        job_service.append_event(
            job_id,
            "metrics_updated",
            {"phase": "repo_loaded", "metrics": {"total_files": 2, "ignored_dirs": 1}},
        )
        job_service.append_event(
            job_id,
            "document_generated",
            {
                "document": {
                    "title": "Overview",
                    "filename": "overview.md",
                    "path": "generated_docs/test/overview.md",
                    "content": "# Overview",
                },
                "index": 1,
                "total": 1,
            },
        )
        job_service.update_status(job_id, "success")
        job_service.append_event(job_id, "job_completed", {"docs_dir": "generated_docs/test"})

    agent_api.run_codebase_analysis_job = fake_runner
    agent_api.Thread = ImmediateThread
    agent_api.require_llm_configuration = lambda: None
    agent_api.analysis_job_service = job_service
    try:
        client = TestClient(create_app())
        response = client.post(
            "/api/agent/analyze/jobs",
            json={"repo_url": "https://github.com/owner/repo"},
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        events_response = client.get(f"/api/agent/analyze/jobs/{job_id}/events")
        assert events_response.status_code == 200
        assert "event: job_started" in events_response.text
        assert "event: metrics_updated" in events_response.text
        assert '"total_files": 2' in events_response.text
        assert "event: document_generated" in events_response.text
        assert "event: job_completed" in events_response.text
    finally:
        agent_api.run_codebase_analysis_job = original_runner
        agent_api.Thread = original_thread
        agent_api.require_llm_configuration = original_require_llm_configuration
        agent_api.analysis_job_service = original_service


def test_mock_analysis_endpoint_is_not_available() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/agent/analyze/mock",
        json={"repo_url": "https://github.com/owner/repo"},
    )

    assert response.status_code == 404