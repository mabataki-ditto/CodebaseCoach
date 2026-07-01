from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.metrics import MockAnalysisMetrics
from app.schemas.repo import BasicFileSummary, FileTreeNode, RepoParseResponse


class AnalyzeRepoRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)


AnalyzeMockRequest = AnalyzeRepoRequest


class CoreFileSummary(BaseModel):
    path: str
    file_type: str
    size: int
    content_preview: str
    truncated: bool
    reason: str
    read_status: str = "read"
    used_for_context: bool = True


AgentStepStatus = Literal["pending", "running", "success", "failed", "skipped"]
ToolCallStatus = Literal["running", "success", "failed", "skipped", "info"]


class AgentStep(BaseModel):
    step_id: str = Field(default_factory=lambda: uuid4().hex)
    id: str = ""
    key: str
    title: str
    status: AgentStepStatus
    description: str
    started_at: str | None = None
    ended_at: str | None = None
    completed_at: str | None = None
    duration_ms: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, _: Any) -> None:
        if not self.id:
            self.id = self.step_id
        if self.completed_at is None:
            self.completed_at = self.ended_at


class ToolCallLog(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    tool_name: str
    status: ToolCallStatus
    input_summary: str
    output_summary: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    related_files: list[str] = Field(default_factory=list)
    duration_ms: int
    created_at: str
    error_message: str | None = None


class GeneratedDocument(BaseModel):
    title: str
    filename: str
    path: str
    content: str


class AnalyzeRepoResponse(RepoParseResponse):
    file_tree: list[FileTreeNode]
    basic_files: list[BasicFileSummary]
    core_files: list[CoreFileSummary]
    agent_steps: list[AgentStep]
    tool_logs: list[ToolCallLog]
    documents: list[GeneratedDocument]
    docs_dir: str
    metrics: MockAnalysisMetrics
    mock_mode: bool = True


MockAnalyzeResponse = AnalyzeRepoResponse
