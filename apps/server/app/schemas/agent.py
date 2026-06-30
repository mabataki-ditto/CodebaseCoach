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


class AgentStep(BaseModel):
    title: str
    status: str
    description: str
    started_at: str
    ended_at: str
    error_message: str | None = None


class ToolCallLog(BaseModel):
    tool_name: str
    status: str
    input_summary: str
    output_summary: str
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
