from typing import Literal

from langgraph.runtime import Runtime

from app.agent.prompts import REAL_DOCUMENT_PROMPTS
from app.agent_graph.context import AnalysisRuntimeContext, check_cancellation
from app.agent_graph.stage_adapter import GraphStageAdapter
from app.agent_graph.state import AnalysisState
from app.schemas.agent import GeneratedDocument, GeneratedResultEvaluation
from app.services.result_evaluation_service import evaluate_generated_documents


MIN_TEXTCITATION_SCORE = 0.7
MAX_HALLUCINATION_RISK = 0.3
MAX_QUALITY_RETRIES = 2


def evaluate_documents(state: AnalysisState) -> AnalysisState:
    """Evaluate in-memory graph documents through the existing deterministic service."""
    documents = [
        GeneratedDocument(title=title, filename=filename, path="", content=content)
        for title, filename, content in state["documents"]
    ]
    core_files = state.get("core_files", [])
    basic_files = state.get("basic_files", [])
    context_file_count = len(basic_files) + len([file for file in core_files if file.used_for_context])
    retry_count = state.get("quality_retry_count", 0)
    input_payload = {
        "document_count": len(documents),
        "context_file_count": context_file_count,
    }
    if retry_count:
        input_payload["quality_retry_count"] = retry_count
    step_key = "evaluate_generated_documents"
    if retry_count:
        step_key = f"{step_key}_retry_{retry_count}"
    adapter = GraphStageAdapter(state)
    evaluation = adapter.run(
        key=step_key,
        title="Evaluate generated documents",
        description="Run deterministic output checks",
        tool_name="evaluate_generated_documents",
        input_summary=f"documents={len(documents)}, context_files={context_file_count}",
        input_payload=input_payload,
        action=lambda: evaluate_generated_documents(
            documents=documents,
            core_files=core_files,
            basic_files=basic_files,
        ),
        output_summary=lambda result: (
            f"Quality scores: citations={result.textcitation_score}, coverage={result.coverage_score}"
        ),
        output_payload=lambda result: {
            "textcitation_score": result.textcitation_score,
            "coverage_score": result.coverage_score,
            "hallucination_risk": result.hallucination_risk,
            "usefulness_score": result.usefulness_score,
            "issue_count": len(result.issues),
        },
        related_files=lambda _: [file.path for file in basic_files]
        + [file.path for file in core_files if file.used_for_context],
    )
    quality_passed = _quality_passed(evaluation)
    return {
        "result_evaluation": evaluation,
        "quality_passed": quality_passed,
        "quality_feedback": "" if quality_passed else _build_quality_feedback(evaluation),
        **adapter.state_update(),
    }


def prepare_quality_retry(
    state: AnalysisState,
    runtime: Runtime[AnalysisRuntimeContext],
) -> AnalysisState:
    check_cancellation(runtime)
    evaluation = state["result_evaluation"]
    indices = _quality_retry_indices(evaluation)
    check_cancellation(runtime)
    return {
        "quality_retry_count": state.get("quality_retry_count", 0) + 1,
        "quality_retry_indices": indices,
    }


def route_after_quality(state: AnalysisState) -> Literal["retry", "end"]:
    if state.get("quality_passed", False):
        return "end"
    if state.get("quality_retry_count", 0) >= MAX_QUALITY_RETRIES:
        return "end"
    return "retry"


def _quality_passed(evaluation: GeneratedResultEvaluation) -> bool:
    return (
        evaluation.textcitation_score >= MIN_TEXTCITATION_SCORE
        and evaluation.hallucination_risk <= MAX_HALLUCINATION_RISK
    )


def _build_quality_feedback(evaluation: GeneratedResultEvaluation) -> str:
    lines = [
        "Quality evaluation feedback for regeneration:",
        f"- textcitation_score: {evaluation.textcitation_score} (required >= {MIN_TEXTCITATION_SCORE})",
        f"- hallucination_risk: {evaluation.hallucination_risk} (required <= {MAX_HALLUCINATION_RISK})",
    ]
    lines.extend(f"- issue: {issue}" for issue in evaluation.issues)
    return "\n".join(lines)


def _quality_retry_indices(evaluation: GeneratedResultEvaluation) -> list[int]:
    filename_to_index = {
        prompt.filename: index for index, prompt in enumerate(REAL_DOCUMENT_PROMPTS)
    }
    indices = {
        filename_to_index[item.filename]
        for item in evaluation.document_evaluations
        if item.issues and item.filename in filename_to_index
    }
    if any("interview question" in issue.lower() for issue in evaluation.issues):
        interview_index = next(
            (
                index
                for index, prompt in enumerate(REAL_DOCUMENT_PROMPTS)
                if prompt.filename.startswith("05")
            ),
            None,
        )
        if interview_index is not None:
            indices.add(interview_index)
    if not indices:
        return list(range(len(REAL_DOCUMENT_PROMPTS)))
    return sorted(indices)
