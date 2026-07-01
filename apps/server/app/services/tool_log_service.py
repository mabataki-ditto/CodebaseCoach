from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.schemas.agent import ToolCallLog


def record_tool_call(
    tool_logs: list[ToolCallLog],
    *,
    tool_name: str,
    status: str,
    input_summary: str,
    output_summary: str,
    duration_ms: int,
    input_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
    related_files: list[str] | None = None,
    error_message: str | None = None,
) -> ToolCallLog:
    log = ToolCallLog(
        id=uuid4().hex,
        tool_name=tool_name,
        status=status,
        input_summary=input_summary,
        output_summary=output_summary,
        input=input_payload or {},
        output=output_payload or {},
        related_files=related_files or [],
        duration_ms=duration_ms,
        created_at=datetime.now(UTC).isoformat(),
        error_message=error_message,
    )
    tool_logs.append(log)
    return log
