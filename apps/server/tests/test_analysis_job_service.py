import unittest

from app.schemas.agent import GeneratedDocument
from app.services.analysis_job_repository import InMemoryAnalysisJobRepository
from app.services.analysis_job_service import AnalysisJobService


class AnalysisJobServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryAnalysisJobRepository()
        self.service = AnalysisJobService(
            job_repository=self.repository,
            event_repository=self.repository,
            artifact_repository=self.repository,
        )

    def test_create_job_and_append_events_with_sequence(self) -> None:
        job = self.service.create_job("https://github.com/owner/repo")

        first = self.service.append_event(job.id, "job_started", {"repo_url": job.repo_url})
        second = self.service.append_event(job.id, "stage_started", {"stage": "clone"})
        events = self.service.get_events_after(job.id, 0)

        self.assertEqual(job.status, "queued")
        self.assertEqual([event.sequence for event in events], [1, 2])
        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)

    def test_update_status_and_cancel_request(self) -> None:
        job = self.service.create_job("https://github.com/owner/repo")

        running = self.service.update_status(job.id, "running", owner="owner", repo="repo", mock_mode=False)
        cancelled_requested = self.service.request_cancel(job.id)

        self.assertEqual(running.status, "running")
        self.assertEqual(running.owner, "owner")
        self.assertEqual(running.repo, "repo")
        self.assertFalse(running.mock_mode)
        self.assertTrue(cancelled_requested.cancel_requested)
        self.assertTrue(self.service.is_cancel_requested(job.id))

    def test_snapshot_returns_documents_artifact(self) -> None:
        job = self.service.create_job("https://github.com/owner/repo")
        document = GeneratedDocument(title="项目概览", filename="01.md", path="generated_docs/demo/01.md", content="# Demo")

        self.service.put_artifact(job.id, "documents", [document.model_dump()])
        snapshot = self.service.get_snapshot(job.id)

        self.assertEqual(len(snapshot.documents), 1)
        self.assertEqual(snapshot.documents[0].filename, "01.md")


if __name__ == "__main__":
    unittest.main()
