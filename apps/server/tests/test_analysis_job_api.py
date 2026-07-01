import unittest

from fastapi.testclient import TestClient

from app.api import agent as agent_api
from app.main import create_app


class AnalysisJobApiTests(unittest.TestCase):
    def test_create_job_and_stream_events(self) -> None:
        original_runner = agent_api.run_codebase_analysis_job

        def fake_runner(*, job_id, repo_url, job_service, force_mock=False):
            job_service.update_status(job_id, "running")
            job_service.append_event(job_id, "job_started", {"repo_url": repo_url, "mock_mode": force_mock})
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


if __name__ == "__main__":
    unittest.main()
