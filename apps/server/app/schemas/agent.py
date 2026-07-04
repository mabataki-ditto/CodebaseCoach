from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.metrics import CoreFileCandidateMetric, MockAnalysisMetrics
from app.schemas.repo import BasicFileSummary, FileTreeNode, RepoParseResponse


class AnalyzeRepoRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)


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
ToolPermission = Literal["read", "network", "llm", "write", "command", "delete"]


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
    tool_provider: str = "builtin"
    tool_name: str
    permission: ToolPermission = "read"
    requires_confirmation: bool = False
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
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


class GeneratedDocumentEvaluation(BaseModel):
    filename: str
    title: str
    has_title: bool
    char_count: int = Field(..., ge=0)
    referenced_file_paths: list[str]
    valid_referenced_file_paths: list[str]
    invalid_referenced_file_paths: list[str]
    placeholder_hits: list[str]
    issues: list[str] = Field(default_factory=list)


class GeneratedResultEvaluation(BaseModel):
    document_count: int = Field(..., ge=0)
    evaluated_document_count: int = Field(..., ge=0)
    textcitation_score: float = Field(..., ge=0, le=1)
    coverage_score: float = Field(..., ge=0, le=1)
    hallucination_risk: float = Field(..., ge=0, le=1)
    usefulness_score: float = Field(..., ge=0, le=1)
    valid_reference_count: int = Field(..., ge=0)
    invalid_reference_count: int = Field(..., ge=0)
    referenced_context_file_count: int = Field(..., ge=0)
    context_file_count: int = Field(..., ge=0)
    interview_question_count: int = Field(..., ge=0)
    interview_question_target: int = Field(..., ge=0)
    document_evaluations: list[GeneratedDocumentEvaluation]
    issues: list[str] = Field(default_factory=list)


class ContextDirectoryCoverage(BaseModel):
    directory: str
    selected_file_count: int = Field(..., ge=0)


class ContextSelectionReasonCount(BaseModel):
    reason: str
    selected_file_count: int = Field(..., ge=0)


class ContextQualityReport(BaseModel):
    candidate_file_count: int = Field(..., ge=0)
    selected_file_count: int = Field(..., ge=0)
    omitted_candidate_count: int = Field(..., ge=0)
    context_char_count: int = Field(..., ge=0)
    raw_candidate_chars: int = Field(..., ge=0)
    compression_ratio: float = Field(..., ge=0)
    truncated_selected_file_count: int = Field(..., ge=0)
    budget_limit_reached: bool
    selected_files: list[str]
    directory_coverage: list[ContextDirectoryCoverage]
    selection_reasons: list[ContextSelectionReasonCount]
    omitted_candidates: list[CoreFileCandidateMetric]
    notes: list[str] = Field(default_factory=list)


class AnalyzeRepoResponse(RepoParseResponse):
    file_tree: list[FileTreeNode]
    basic_files: list[BasicFileSummary]
    core_files: list[CoreFileSummary]
    context_quality_report: ContextQualityReport
    agent_steps: list[AgentStep]
    tool_logs: list[ToolCallLog]
    documents: list[GeneratedDocument]
    result_evaluation: GeneratedResultEvaluation
    docs_dir: str
    metrics: MockAnalysisMetrics
    mock_mode: bool = True
