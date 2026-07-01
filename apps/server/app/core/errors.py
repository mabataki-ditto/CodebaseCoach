from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
    agent_steps: list[dict[str, Any]] = Field(default_factory=list)
    tool_logs: list[dict[str, Any]] = Field(default_factory=list)


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        detail: str | None = None,
        agent_steps: list[Any] | None = None,
        tool_logs: list[Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        self.agent_steps = agent_steps or []
        self.tool_logs = tool_logs or []


def build_error_response(error: AppError) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorDetail(
            code=error.code,
            message=error.message,
            detail=error.detail,
        ),
        agent_steps=[_dump_model(item) for item in error.agent_steps],
        tool_logs=[_dump_model(item) for item in error.tool_logs],
    )


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value
