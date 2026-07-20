"""State shared by the incremental analysis graph.

Repository data, document outputs, and audit records are business values.
``local_path`` is a process-local filesystem reference and is not a durable
recovery point. MCP clients and LLM credentials live in runtime context rather
than state. No checkpointer is configured through Phase 4.
"""

from typing import TypedDict

from app.core.errors import ErrorDetail
from app.schemas.agent import (
    AgentStep,
    ContextQualityReport,
    CoreFileSummary,
    GeneratedResultEvaluation,
    ToolCallLog,
)
from app.schemas.metrics import CoreFileSelectionMetrics, RepoScanMetrics
from app.schemas.repo import BasicFileSummary, FileTreeNode, RepoParseResponse
from app.services.llm_call_service import LLMCallRecord


class AnalysisState(TypedDict, total=False):
    job_id: str
    repo_url: str
    parsed_repo: RepoParseResponse
    local_path: str
    repository_commit_sha: str
    recovery_source_commit_sha: str
    recovery_mode: str
    file_tree: list[FileTreeNode]
    basic_files: list[BasicFileSummary]
    core_files: list[CoreFileSummary]
    selection_metrics: CoreFileSelectionMetrics
    repo_scan_metrics: RepoScanMetrics
    context_quality_report: ContextQualityReport
    analysis_context: str
    github_mcp_context: str
    documents: list[tuple[str, str, str]]
    llm_call_records: list[LLMCallRecord]
    result_evaluation: GeneratedResultEvaluation
    quality_passed: bool
    quality_retry_count: int
    quality_retry_indices: list[int]
    quality_feedback: str
    agent_steps: list[AgentStep]
    tool_logs: list[ToolCallLog]
    error: ErrorDetail | None
