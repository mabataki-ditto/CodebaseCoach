import unittest

from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.main import create_app
from app.services.analysis_job_repository import InMemoryAnalysisJobRepository
from app.services.analysis_job_service import AnalysisJobService


class AnalysisJobApiTests(unittest.TestCase):
    def setUp(self) -> None:
        repository = InMemoryAnalysisJobRepository()
        self._original_service = agent_api.analysis_job_service
        agent_api.analysis_job_service = AnalysisJobService(
            job_repository=repository,
            event_repository=repository,
            artifact_repository=repository,
        )

    def tearDown(self) -> None:
        agent_api.analysis_job_service = self._original_service

    def test_create_job_and_stream_events(self) -> None:
        original_runner = agent_api.run_codebase_analysis_job
        original_thread = agent_api.Thread
        original_require_llm_configuration = agent_api.require_llm_configuration

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
        try:
            client = TestClient(create_app())
            response = client.post(
                "/api/agent/analyze/jobs",
                json={"repo_url": "https://github.com/owner/repo"},
            )
            self.assertEqual(response.status_code, 200)
            job_id = response.json()["job_id"]

            events_response = client.get(f"/api/agent/analyze/jobs/{job_id}/events")
            self.assertEqual(events_response.status_code, 200)
            self.assertIn("event: job_started", events_response.text)
            self.assertIn("event: metrics_updated", events_response.text)
            self.assertIn('"total_files": 2', events_response.text)
            self.assertIn("event: document_generated", events_response.text)
            self.assertIn("event: job_completed", events_response.text)
        finally:
            agent_api.run_codebase_analysis_job = original_runner
            agent_api.Thread = original_thread
            agent_api.require_llm_configuration = original_require_llm_configuration

    def test_mock_analysis_endpoint_is_not_available(self) -> None:
        client = TestClient(create_app())

        response = client.post(
            "/api/agent/analyze/mock",
            json={"repo_url": "https://github.com/owner/repo"},
        )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
