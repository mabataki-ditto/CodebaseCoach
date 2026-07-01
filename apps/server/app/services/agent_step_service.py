from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.schemas.agent import AgentStep


class AgentStepRecorder:
    def __init__(self, steps: list[AgentStep]) -> None:
        self._steps = steps
        self._started_by_id: dict[str, float] = {}

    @property
    def steps(self) -> list[AgentStep]:
        return self._steps

    def start(
        self,
        *,
        key: str,
        title: str,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        step_id = uuid4().hex
        step = AgentStep(
            step_id=step_id,
            id=step_id,
            key=key,
            title=title,
            status="running",
            description=description,
            started_at=_now(),
            metadata=metadata or {},
        )
        self._steps.append(step)
        self._started_by_id[step.id] = perf_counter()
        return step

    def succeed(self, step: AgentStep, *, metadata: dict[str, Any] | None = None) -> None:
        self._finish(step, status="success", metadata=metadata)

    def fail(self, step: AgentStep, *, error_message: str, metadata: dict[str, Any] | None = None) -> None:
        self._finish(step, status="failed", error_message=error_message, metadata=metadata)

    def skip(
        self,
        *,
        key: str,
        title: str,
        description: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        completed_at = _now()
        step_id = uuid4().hex
        step = AgentStep(
            step_id=step_id,
            id=step_id,
            key=key,
            title=title,
            status="skipped",
            description=description,
            started_at=completed_at,
            ended_at=completed_at,
            completed_at=completed_at,
            error_message=reason,
            metadata=metadata or {},
        )
        self._steps.append(step)
        return step

    def _finish(
        self,
        step: AgentStep,
        *,
        status: str,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        started = self._started_by_id.pop(step.id, None)
        step.status = status
        completed_at = _now()
        step.ended_at = completed_at
        step.completed_at = completed_at
        step.duration_ms = int((perf_counter() - started) * 1000) if started is not None else 0
        step.error_message = error_message
        if metadata:
            step.metadata.update(metadata)


def _now() -> str:
    return datetime.now(UTC).isoformat()
