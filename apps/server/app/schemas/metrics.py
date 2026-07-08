from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


RepoOperation = Literal["repo_parse", "repo_scan", "agent_analyze_mock", "agent_analyze"]
MetricStatus = Literal["success", "failed"]


class CoreFileSelectionMetrics(BaseModel):
    candidate_core_files: int = Field(default=0, ge=0)
    raw_candidate_chars: int = Field(default=0, ge=0)
    candidates: list["CoreFileCandidateMetric"] = Field(default_factory=list)


class CoreFileCandidateMetric(BaseModel):
    path: str
    file_type: str
    size: int = Field(..., ge=0)
    reason: str
    score: int = Field(..., ge=0)
    truncated: bool = False


class RepoScanMetrics(BaseModel):
    total_files: int = Field(default=0, ge=0)
    ignored_dirs: int = Field(default=0, ge=0)


class MockAnalysisMetrics(CoreFileSelectionMetrics):
    total_files: int = Field(default=0, ge=0)
    ignored_dirs: int = Field(default=0, ge=0)
    selected_core_files: int = Field(default=0, ge=0)
    read_files: int = Field(default=0, ge=0)
    truncated_files: int = Field(default=0, ge=0)
    final_context_chars: int = Field(default=0, ge=0)
    context_compression_ratio: float = Field(default=0, ge=0)
    analysis_duration_ms: int = Field(default=0, ge=0)
    used_mock_ai: bool = True
    provider: str = ""
    model: str = ""
    llm_call_count: int = Field(default=0, ge=0)
    llm_success_count: int = Field(default=0, ge=0)
    llm_failed_count: int = Field(default=0, ge=0)
    llm_total_duration_ms: int = Field(default=0, ge=0)
    llm_input_tokens: int = Field(default=0, ge=0)
    llm_output_tokens: int = Field(default=0, ge=0)
    llm_total_tokens: int = Field(default=0, ge=0)
    generated_doc_count: int = Field(default=0, ge=0)
    generated_doc_total_chars: int = Field(default=0, ge=0)
    generated_doc_total_words: int = Field(default=0, ge=0)
    interview_question_count: int = Field(default=0, ge=0)
    referenced_file_path_count: int = Field(default=0, ge=0)
    prompt_template_count: int = Field(default=0, ge=0)
    agent_step_count: int = Field(default=0, ge=0)
    agent_success_step_count: int = Field(default=0, ge=0)
    agent_failed_step_count: int = Field(default=0, ge=0)
    agent_skipped_step_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    tool_success_count: int = Field(default=0, ge=0)
    tool_failed_count: int = Field(default=0, ge=0)
    avg_tool_duration_ms: int = Field(default=0, ge=0)
    max_tool_duration_ms: int = Field(default=0, ge=0)
    total_tool_duration_ms: int = Field(default=0, ge=0)


class RepoOperationMetrics(BaseModel):
    record_id: str = Field(default_factory=lambda: uuid4().hex)
    operation: RepoOperation
    status: MetricStatus
    repo_url: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int = Field(..., ge=0)
    owner: str | None = None
    repo: str | None = None
    cloned: bool = False
    file_tree_node_count: int = Field(default=0, ge=0)
    basic_file_count: int = Field(default=0, ge=0)
    basic_file_bytes: int = Field(default=0, ge=0)
    total_files: int = Field(default=0, ge=0)
    ignored_dirs: int = Field(default=0, ge=0)
    candidate_core_files: int = Field(default=0, ge=0)
    selected_core_files: int = Field(default=0, ge=0)
    read_files: int = Field(default=0, ge=0)
    truncated_files: int = Field(default=0, ge=0)
    raw_candidate_chars: int = Field(default=0, ge=0)
    final_context_chars: int = Field(default=0, ge=0)
    context_compression_ratio: float = Field(default=0, ge=0)
    analysis_duration_ms: int = Field(default=0, ge=0)
    used_mock_ai: bool = True
    provider: str = ""
    model: str = ""
    llm_call_count: int = Field(default=0, ge=0)
    llm_success_count: int = Field(default=0, ge=0)
    llm_failed_count: int = Field(default=0, ge=0)
    llm_total_duration_ms: int = Field(default=0, ge=0)
    llm_input_tokens: int = Field(default=0, ge=0)
    llm_output_tokens: int = Field(default=0, ge=0)
    llm_total_tokens: int = Field(default=0, ge=0)
    generated_doc_count: int = Field(default=0, ge=0)
    generated_doc_total_chars: int = Field(default=0, ge=0)
    generated_doc_total_words: int = Field(default=0, ge=0)
    interview_question_count: int = Field(default=0, ge=0)
    referenced_file_path_count: int = Field(default=0, ge=0)
    prompt_template_count: int = Field(default=0, ge=0)
    agent_step_count: int = Field(default=0, ge=0)
    agent_success_step_count: int = Field(default=0, ge=0)
    agent_failed_step_count: int = Field(default=0, ge=0)
    agent_skipped_step_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    tool_success_count: int = Field(default=0, ge=0)
    tool_failed_count: int = Field(default=0, ge=0)
    avg_tool_duration_ms: int = Field(default=0, ge=0)
    max_tool_duration_ms: int = Field(default=0, ge=0)
    total_tool_duration_ms: int = Field(default=0, ge=0)
    error_code: str | None = None
    error_message: str | None = None
