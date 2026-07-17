import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any, TypeVar

from langgraph.config import get_stream_writer

from app.agent.tools import assert_tool_allowed
from app.agent_graph.state import AnalysisState
from app.core.errors import AppError
from app.schemas.agent import AgentStep, ToolCallLog
from app.services.agent_step_service import AgentStepRecorder
from app.services.tool_log_service import record_tool_call

T = TypeVar("T")

logger = logging.getLogger(__name__)


class GraphStageAdapter:
    """Record graph node work with the existing step and tool-log schemas."""

    def __init__(self, state: AnalysisState) -> None:
        self._tool_logs = list(state.get("tool_logs", []))
        self._step_recorder = AgentStepRecorder(list(state.get("agent_steps", [])))

    @property
    def tool_logs(self) -> list[ToolCallLog]:
        return self._tool_logs

    def run(
        self,
        *,
        key: str,
        title: str,
        description: str,
        tool_name: str,
        input_summary: str,
        input_payload: dict[str, Any],
        action: Callable[[], T],
        output_summary: Callable[[T], str],
        output_payload: Callable[[T], dict[str, Any]],
        related_files: Callable[[T], list[str]] | None = None,
    ) -> T:
        assert_tool_allowed(tool_name)
        step = self._step_recorder.start(
            key=key,
            title=title,
            description=description,
            metadata={"tool_name": tool_name, "input": input_payload},
        )
        self._emit(
            event_id=f"{step.id}:started",
            event_type="stage_started",
            payload={"key": key, "title": title, "description": description},
        )
        started = perf_counter()
        try:
            result = action()
        except AppError as error:
            self._record_failure(step, tool_name, input_summary, input_payload, started, error)
            self._emit(
                event_id=f"{step.id}:failed",
                event_type="stage_failed",
                payload={
                    "key": key,
                    "title": title,
                    "code": error.code,
                    "message": error.message,
                    "detail": error.detail,
                },
            )
            raise
        except Exception as error:
            app_error = AppError(
                status_code=500,
                code="UNKNOWN_ERROR",
                message="Codebase analysis workflow failed",
                detail=str(error),
            )
            self._record_failure(step, tool_name, input_summary, input_payload, started, app_error)
            self._emit(
                event_id=f"{step.id}:failed",
                event_type="stage_failed",
                payload={
                    "key": key,
                    "title": title,
                    "code": app_error.code,
                    "message": app_error.message,
                    "detail": app_error.detail,
                },
            )
            raise app_error from error

        duration_ms = int((perf_counter() - started) * 1000)
        output = output_payload(result)
        related = related_files(result) if related_files else []
        self._step_recorder.succeed(step, metadata={"output": output, "related_files": related})
        record_tool_call(
            self._tool_logs,
            tool_name=tool_name,
            status="success",
            input_summary=input_summary,
            output_summary=output_summary(result),
            input_payload=input_payload,
            output_payload=output,
            related_files=related,
            duration_ms=duration_ms,
        )
        self._emit(
            event_id=f"{step.id}:completed",
            event_type="stage_completed",
            payload={"key": key, "title": title, "output": output},
        )
        return result

    def skip(
        self,
        *,
        key: str,
        title: str,
        description: str,
        tool_name: str,
        reason: str,
        input_payload: dict[str, Any],
    ) -> None:
        assert_tool_allowed(tool_name)
        step = self._step_recorder.skip(
            key=key,
            title=title,
            description=description,
            reason=reason,
            metadata={"tool_name": tool_name, "input": input_payload},
        )
        self._emit(
            event_id=f"{step.id}:started",
            event_type="stage_started",
            payload={"key": key, "title": title, "description": description},
        )
        record_tool_call(
            self._tool_logs,
            tool_name=tool_name,
            status="skipped",
            input_summary=reason,
            output_summary="Skipped",
            input_payload=input_payload,
            output_payload={"reason": reason},
            duration_ms=0,
            error_message=reason,
        )
        self._emit(
            event_id=f"{step.id}:completed",
            event_type="stage_completed",
            payload={"key": key, "title": title, "output": {"reason": reason, "status": "skipped"}},
        )

    def state_update(self) -> AnalysisState:
        return {
            "agent_steps": list(self._step_recorder.steps),
            "tool_logs": list(self._tool_logs),
        }

    def _record_failure(
        self,
        step: AgentStep,
        tool_name: str,
        input_summary: str,
        input_payload: dict[str, Any],
        started: float,
        error: AppError,
    ) -> None:
        duration_ms = int((perf_counter() - started) * 1000)
        logger.error("[graph-stage] failed: %s | code=%s", step.title, error.code)
        self._step_recorder.fail(
            step,
            error_message=error.message,
            metadata={"error_code": error.code, "error_detail": error.detail},
        )
        record_tool_call(
            self._tool_logs,
            tool_name=tool_name,
            status="failed",
            input_summary=input_summary,
            output_summary="Failed",
            input_payload=input_payload,
            output_payload={"error_code": error.code},
            duration_ms=duration_ms,
            error_message=error.detail or error.message,
        )
        error.agent_steps = list(self._step_recorder.steps)
        error.tool_logs = list(self._tool_logs)

    @staticmethod
    def _emit(*, event_id: str, event_type: str, payload: dict[str, Any]) -> None:
        try:
            writer = get_stream_writer()
        except RuntimeError:
            return
        writer({"event_id": event_id, "type": event_type, "payload": payload})
