from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.agent import AnalyzeRepoResponse, CoreFileSummary, GeneratedDocument
from app.schemas.metrics import MockAnalysisMetrics
from app.schemas.repo import BasicFileSummary, FileTreeNode


AnalysisJobStatus = Literal["queued", "running", "success", "failed", "cancelled"]
AnalysisRecoveryMode = Literal["checkpoint", "rebuild_repository", "full_restart"]
AnalysisEventType = Literal[
    "job_started",
    "stage_started",
    "stage_completed",
    "stage_failed",
    "metrics_updated",
    "document_generated",
    "job_completed",
    "job_failed",
    "job_cancelled",
]


class AnalysisJob(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    repo_url: str
    owner: str = ""
    repo: str = ""
    status: AnalysisJobStatus = "queued"
    created_at: str
    updated_at: str
    completed_at: str | None = None
    docs_dir: str = ""
    core_files_count: int = 0
    error_message: str | None = None
    metrics: MockAnalysisMetrics | None = None
    mock_mode: bool = True
    cancel_requested: bool = False


class AnalysisEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    job_id: str
    type: AnalysisEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    sequence: int


class AnalysisArtifact(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    job_id: str
    artifact_type: str
    payload: Any = Field(default_factory=dict)
    created_at: str


class AnalysisJobCreateResponse(BaseModel):
    job_id: str
    status: AnalysisJobStatus


class AnalysisJobSnapshot(BaseModel):
    job: AnalysisJob
    events: list[AnalysisEvent]
    file_tree: list[FileTreeNode] = Field(default_factory=list)
    basic_files: list[BasicFileSummary] = Field(default_factory=list)
    core_files: list[CoreFileSummary] = Field(default_factory=list)
    documents: list[GeneratedDocument] = Field(default_factory=list)
    result: AnalyzeRepoResponse | None = None


class AnalysisJobCancelResponse(BaseModel):
    job_id: str
    status: AnalysisJobStatus


class AnalysisJobResumeStatusResponse(BaseModel):
    job_id: str
    can_resume: bool
    job_status: AnalysisJobStatus
    engine: str | None = None
    recovery_mode: AnalysisRecoveryMode | None = None
    reason: str | None = None


class AnalysisJobResumeResponse(BaseModel):
    job_id: str
    status: AnalysisJobStatus
    resumed: bool
    recovery_mode: AnalysisRecoveryMode
