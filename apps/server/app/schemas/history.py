from pydantic import BaseModel, Field


class HistoryRecord(BaseModel):
    id: str
    repo_url: str
    owner: str
    repo: str
    status: str
    created_at: str
    completed_at: str | None = None
    docs_dir: str = ""
    core_files_count: int = Field(default=0, ge=0)
    error_message: str | None = None
    mock_mode: bool = True


class HistoryListResponse(BaseModel):
    records: list[HistoryRecord]
