from abc import ABC, abstractmethod
from copy import deepcopy
from threading import RLock

from app.schemas.analysis_job import AnalysisArtifact, AnalysisEvent, AnalysisJob


class AnalysisJobRepository(ABC):
    @abstractmethod
    def create_job(self, job: AnalysisJob) -> AnalysisJob:
        raise NotImplementedError

    @abstractmethod
    def get_job(self, job_id: str) -> AnalysisJob | None:
        raise NotImplementedError

    @abstractmethod
    def update_job(self, job: AnalysisJob) -> AnalysisJob:
        raise NotImplementedError

    @abstractmethod
    def try_transition_status(
        self,
        job_id: str,
        *,
        expected_statuses: set[str],
        new_status: str,
    ) -> AnalysisJob | None:
        raise NotImplementedError


class AnalysisEventRepository(ABC):
    @abstractmethod
    def append_event(self, event: AnalysisEvent) -> AnalysisEvent:
        raise NotImplementedError

    @abstractmethod
    def get_events_after(self, job_id: str, sequence: int) -> list[AnalysisEvent]:
        raise NotImplementedError

    @abstractmethod
    def next_sequence(self, job_id: str) -> int:
        raise NotImplementedError


class AnalysisArtifactRepository(ABC):
    @abstractmethod
    def put_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        raise NotImplementedError

    @abstractmethod
    def list_artifacts(self, job_id: str, artifact_type: str | None = None) -> list[AnalysisArtifact]:
        raise NotImplementedError


class InMemoryAnalysisJobRepository(AnalysisJobRepository, AnalysisEventRepository, AnalysisArtifactRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, AnalysisJob] = {}
        self._events: dict[str, list[AnalysisEvent]] = {}
        self._artifacts: dict[str, list[AnalysisArtifact]] = {}

    def create_job(self, job: AnalysisJob) -> AnalysisJob:
        with self._lock:
            self._jobs[job.id] = job.model_copy(deep=True)
            self._events.setdefault(job.id, [])
            self._artifacts.setdefault(job.id, [])
            return job.model_copy(deep=True)

    def get_job(self, job_id: str) -> AnalysisJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def update_job(self, job: AnalysisJob) -> AnalysisJob:
        with self._lock:
            self._jobs[job.id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def try_transition_status(
        self,
        job_id: str,
        *,
        expected_statuses: set[str],
        new_status: str,
    ) -> AnalysisJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in expected_statuses:
                return None
            updated = job.model_copy(deep=True)
            updated.status = new_status
            self._jobs[job_id] = updated
            return updated.model_copy(deep=True)

    def append_event(self, event: AnalysisEvent) -> AnalysisEvent:
        with self._lock:
            self._events.setdefault(event.job_id, []).append(event.model_copy(deep=True))
            return event.model_copy(deep=True)

    def get_events_after(self, job_id: str, sequence: int) -> list[AnalysisEvent]:
        with self._lock:
            return [
                event.model_copy(deep=True)
                for event in self._events.get(job_id, [])
                if event.sequence > sequence
            ]

    def next_sequence(self, job_id: str) -> int:
        with self._lock:
            return len(self._events.get(job_id, [])) + 1

    def put_artifact(self, artifact: AnalysisArtifact) -> AnalysisArtifact:
        with self._lock:
            artifacts = self._artifacts.setdefault(artifact.job_id, [])
            artifacts = [item for item in artifacts if item.artifact_type != artifact.artifact_type]
            artifacts.append(artifact.model_copy(deep=True))
            self._artifacts[artifact.job_id] = artifacts
            return artifact.model_copy(deep=True)

    def list_artifacts(self, job_id: str, artifact_type: str | None = None) -> list[AnalysisArtifact]:
        with self._lock:
            artifacts = self._artifacts.get(job_id, [])
            if artifact_type is not None:
                artifacts = [artifact for artifact in artifacts if artifact.artifact_type == artifact_type]
            return deepcopy(artifacts)
