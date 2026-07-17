from typing import Any, cast

from app.schemas.analysis_job import AnalysisEventType
from app.services.analysis_job_service import AnalysisJobService


_SSE_EVENT_TYPES: set[str] = {
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


class LangGraphEventAdapter:
    """Translate graph custom events into the existing persisted SSE contract."""

    def __init__(self, *, job_id: str, job_service: AnalysisJobService) -> None:
        self._job_id = job_id
        self._job_service = job_service
        self._seen_event_ids: set[str] = set()

    def handle_custom_event(self, event: dict[str, Any]) -> None:
        event_id = str(event.get("event_id", ""))
        if event_id and event_id in self._seen_event_ids:
            return
        event_type = str(event.get("type", ""))
        if event_type not in _SSE_EVENT_TYPES:
            return
        if event_id:
            self._seen_event_ids.add(event_id)
        payload = event.get("payload")
        self._job_service.append_event(
            self._job_id,
            cast(AnalysisEventType, event_type),
            payload if isinstance(payload, dict) else {},
        )

    def append(self, event_type: AnalysisEventType, payload: dict[str, Any]) -> None:
        self._job_service.append_event(self._job_id, event_type, payload)
