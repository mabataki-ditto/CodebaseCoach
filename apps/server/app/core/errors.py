from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail


def build_error_response(error: AppError) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorDetail(
            code=error.code,
            message=error.message,
            detail=error.detail,
        )
    )
