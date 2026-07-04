from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.agent.tools import ToolDefinition, get_tool_definition, redact_tool_payload
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
    definition: ToolDefinition | None = None,
) -> ToolCallLog:
    definition = definition or get_tool_definition(tool_name)
    input_payload = input_payload or {}
    output_payload = output_payload or {}
    log = ToolCallLog(
        id=uuid4().hex,
        tool_provider=definition.provider,
        tool_name=tool_name,
        permission=definition.permission,
        requires_confirmation=definition.requires_confirmation,
        input_schema=definition.input_schema,
        output_schema=definition.output_schema,
        status=status,
        input_summary=input_summary,
        output_summary=output_summary,
        input=redact_tool_payload(input_payload, definition=definition),
        output=redact_tool_payload(output_payload, definition=definition),
        related_files=related_files or [],
        duration_ms=duration_ms,
        created_at=datetime.now(UTC).isoformat(),
        error_message=error_message,
    )
    tool_logs.append(log)
    return log
