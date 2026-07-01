from fastapi import APIRouter

from app.core.config import settings
from app.core.errors import AppError
from app.schemas.docs import DocsResponse
from app.services.doc_storage_service import load_markdown_documents_for_history
from app.services.history_service import get_history_record

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.get("/{history_id}", response_model=DocsResponse)
def get_docs(history_id: str) -> DocsResponse:
    record = get_history_record(history_file=settings.history_path, record_id=history_id)
    if record is None:
        raise AppError(
            status_code=404,
            code="HISTORY_RECORD_NOT_FOUND",
            message="历史记录不存在",
            detail=history_id,
        )
    documents = load_markdown_documents_for_history(
        docs_root=settings.generated_docs_path,
        history_record=record,
    )
    return DocsResponse(history_id=record.id, docs_dir=record.docs_dir, documents=documents)
