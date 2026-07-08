import re
from collections import Counter
from pathlib import Path

from app.schemas.agent import (
    AgentStep,
    ContextDirectoryCoverage,
    ContextQualityReport,
    ContextSelectionReasonCount,
    CoreFileSummary,
    GeneratedDocument,
    ToolCallLog,
)
from app.schemas.metrics import CoreFileSelectionMetrics, MockAnalysisMetrics, RepoOperationMetrics, RepoScanMetrics
from app.schemas.repo import FileTreeNode
from app.services.llm_call_service import LLMCallRecord


def record_repo_operation_metrics(record: RepoOperationMetrics, *, metrics_file: Path) -> None:
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    line = record.model_dump_json() + "\n"
    with metrics_file.open("a", encoding="utf-8") as file:
        file.write(line)


def count_file_tree_nodes(nodes: list[FileTreeNode]) -> int:
    return sum(1 + count_file_tree_nodes(node.children) for node in nodes)


_INTERVIEW_QUESTION_PATTERN = re.compile(r"^\s*#{2,3}\s+(?:Q\s*)?\d+\s*[：:.、]", re.MULTILINE)
_BACKTICK_TOKEN_PATTERN = re.compile(r"`([^`]+)`")
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_WORD_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")
_MAX_OMITTED_CONTEXT_CANDIDATES = 5
_INTERVIEW_DOC_FILENAME = "05-面试问题与回答.md"


def _count_words(content: str) -> int:
    return len(_CJK_PATTERN.findall(content)) + len(_WORD_TOKEN_PATTERN.findall(content))


def _count_interview_questions(documents: list[GeneratedDocument]) -> int:
    for document in documents:
        if document.filename == _INTERVIEW_DOC_FILENAME:
            return len(_INTERVIEW_QUESTION_PATTERN.findall(document.content))
    return 0


def _count_referenced_file_paths(documents: list[GeneratedDocument]) -> int:
    paths: set[str] = set()
    for document in documents:
        for match in _BACKTICK_TOKEN_PATTERN.finditer(document.content):
            token = match.group(1).strip()
            if "/" in token or re.search(r"\.[A-Za-z][A-Za-z0-9]*$", token):
                paths.add(token)
    return len(paths)


def build_context_quality_report(
    *,
    selection_metrics: CoreFileSelectionMetrics,
    core_files: list[CoreFileSummary],
) -> ContextQualityReport:
    selected_paths = {file.path for file in core_files}
    omitted_candidates = [candidate for candidate in selection_metrics.candidates if candidate.path not in selected_paths]
    context_char_count = sum(len(file.content_preview) for file in core_files)
    raw_candidate_chars = selection_metrics.raw_candidate_chars
    directory_counts = Counter(_top_level_directory(file.path) for file in core_files)
    reason_counts = Counter(file.reason for file in core_files)
    truncated_count = sum(1 for file in core_files if file.truncated)

    notes: list[str] = []
    if not core_files:
        notes.append("No files were selected for LLM context.")
    if omitted_candidates:
        notes.append("Context file limit excluded additional candidate files.")
    if truncated_count:
        notes.append("Some selected files were truncated by the byte budget.")

    return ContextQualityReport(
        candidate_file_count=selection_metrics.candidate_core_files,
        selected_file_count=len(core_files),
        omitted_candidate_count=len(omitted_candidates),
        context_char_count=context_char_count,
        raw_candidate_chars=raw_candidate_chars,
        compression_ratio=context_char_count / raw_candidate_chars if raw_candidate_chars else 0,
        truncated_selected_file_count=truncated_count,
        budget_limit_reached=bool(omitted_candidates),
        selected_files=[file.path for file in core_files],
        directory_coverage=[
            ContextDirectoryCoverage(directory=directory, selected_file_count=count)
            for directory, count in sorted(directory_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        selection_reasons=[
            ContextSelectionReasonCount(reason=reason, selected_file_count=count)
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        omitted_candidates=omitted_candidates[:_MAX_OMITTED_CONTEXT_CANDIDATES],
        notes=notes,
    )


def _top_level_directory(path: str) -> str:
    parts = path.split("/", 1)
    return "." if len(parts) == 1 else parts[0]


def build_mock_analysis_metrics(
    *,
    selection_metrics: CoreFileSelectionMetrics,
    core_files: list[CoreFileSummary],
    documents: list[GeneratedDocument],
    analysis_duration_ms: int,
    used_mock_ai: bool = True,
    provider: str = "",
    model: str = "",
    prompt_template_count: int = 0,
    llm_call_records: list[LLMCallRecord] | None = None,
    agent_steps: list[AgentStep] | None = None,
    tool_logs: list[ToolCallLog] | None = None,
    repo_scan_metrics: RepoScanMetrics | None = None,
) -> MockAnalysisMetrics:
    final_context_chars = sum(len(file.content_preview) for file in core_files)
    raw_candidate_chars = selection_metrics.raw_candidate_chars
    compression_ratio = final_context_chars / raw_candidate_chars if raw_candidate_chars else 0

    records = llm_call_records or []
    llm_call_count = len(records)
    llm_success_count = sum(1 for record in records if record.status == "success")
    llm_failed_count = sum(1 for record in records if record.status == "failed")
    llm_total_duration_ms = sum(record.duration_ms for record in records)
    llm_input_tokens = sum(record.input_tokens or 0 for record in records)
    llm_output_tokens = sum(record.output_tokens or 0 for record in records)
    llm_total_tokens = sum(record.total_tokens or 0 for record in records)

    generated_doc_count = len(documents)
    generated_doc_total_chars = sum(len(document.content) for document in documents)
    generated_doc_total_words = sum(_count_words(document.content) for document in documents)
    interview_question_count = _count_interview_questions(documents)
    referenced_file_path_count = _count_referenced_file_paths(documents)
    steps = agent_steps or []
    logs = tool_logs or []
    total_tool_duration_ms = sum(log.duration_ms for log in logs)
    tool_call_count = len(logs)
    scan_metrics = repo_scan_metrics or RepoScanMetrics()

    return MockAnalysisMetrics(
        total_files=scan_metrics.total_files,
        ignored_dirs=scan_metrics.ignored_dirs,
        candidate_core_files=selection_metrics.candidate_core_files,
        selected_core_files=len(core_files),
        read_files=len(core_files),
        truncated_files=sum(1 for file in core_files if file.truncated),
        raw_candidate_chars=raw_candidate_chars,
        final_context_chars=final_context_chars,
        context_compression_ratio=compression_ratio,
        analysis_duration_ms=analysis_duration_ms,
        used_mock_ai=used_mock_ai,
        provider=provider,
        model=model,
        llm_call_count=llm_call_count,
        llm_success_count=llm_success_count,
        llm_failed_count=llm_failed_count,
        llm_total_duration_ms=llm_total_duration_ms,
        llm_input_tokens=llm_input_tokens,
        llm_output_tokens=llm_output_tokens,
        llm_total_tokens=llm_total_tokens,
        generated_doc_count=generated_doc_count,
        generated_doc_total_chars=generated_doc_total_chars,
        generated_doc_total_words=generated_doc_total_words,
        interview_question_count=interview_question_count,
        referenced_file_path_count=referenced_file_path_count,
        prompt_template_count=prompt_template_count,
        agent_step_count=len(steps),
        agent_success_step_count=sum(1 for step in steps if step.status == "success"),
        agent_failed_step_count=sum(1 for step in steps if step.status == "failed"),
        agent_skipped_step_count=sum(1 for step in steps if step.status == "skipped"),
        tool_call_count=tool_call_count,
        tool_success_count=sum(1 for log in logs if log.status == "success"),
        tool_failed_count=sum(1 for log in logs if log.status == "failed"),
        avg_tool_duration_ms=round(total_tool_duration_ms / tool_call_count) if tool_call_count else 0,
        max_tool_duration_ms=max((log.duration_ms for log in logs), default=0),
        total_tool_duration_ms=total_tool_duration_ms,
    )
