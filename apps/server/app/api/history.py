from fastapi import APIRouter

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.history import HistoryListResponse
from app.services.history_service import delete_history_record, list_history_records

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryListResponse)
def list_history() -> HistoryListResponse:
    return HistoryListResponse(records=list_history_records(history_file=settings.history_path))


@router.delete("/{record_id}")
def delete_history(record_id: str) -> dict[str, bool]:
    deleted = delete_history_record(history_file=settings.history_path, record_id=record_id)
    if not deleted:
        raise AppError(
            status_code=404,
            code="HISTORY_RECORD_NOT_FOUND",
            message="历史记录不存在",
            detail=record_id,
        )
    return {"deleted": True}
