from pathlib import Path

import pytest

import app.agent_graph.nodes.clone_repo as clone_repo_module
import app.agent_graph.nodes.evaluate_documents as evaluate_node_module
import app.agent_graph.nodes.generate_document as generate_document_module
from app.agent.prompts import REAL_DOCUMENT_PROMPTS
from app.agent_graph.graph_builder import build_analysis_graph
from app.agent_graph.nodes.evaluate_documents import evaluate_documents
from app.agent_graph.runner import run_analysis_graph
from app.core.errors import AppError
from app.schemas.agent import CoreFileSummary, GeneratedResultEvaluation

pytestmark = pytest.mark.unit


def _create_sample_repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "README.md").write_text("# Sample\n", encoding="utf-8")
    (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")


def _core_file() -> CoreFileSummary:
    return CoreFileSummary(
        path="README.md",
        file_type="markdown",
        size=8,
        content_preview="# Sample",
        truncated=False,
        reason="project overview",
    )


def _quality_result(*, passed: bool) -> GeneratedResultEvaluation:
    return GeneratedResultEvaluation(
        document_count=7,
        evaluated_document_count=7,
        textcitation_score=1 if passed else 0.5,
        coverage_score=1,
        hallucination_risk=0 if passed else 0.5,
        usefulness_score=1 if passed else 0.4,
        valid_reference_count=7 if passed else 1,
        invalid_reference_count=0 if passed else 1,
        referenced_context_file_count=1,
        context_file_count=1,
        interview_question_count=8,
        interview_question_target=8,
        document_evaluations=[],
        issues=[] if passed else ["01-overview.md: references files outside current context: missing.py."],
    )


def _install_fake_generation(monkeypatch, contexts: list[str]) -> None:
    def fake_generate_document(*, document_prompt, context, api_key, model, base_url, recorder):
        contexts.append(context)
        recorder.record(
            prompt_type=document_prompt.title,
            duration_ms=1,
            status="success",
            total_tokens=1,
        )
        return document_prompt.title, document_prompt.filename, f"# {document_prompt.title}\n\n## Files\n\n`README.md`"

    monkeypatch.setattr(generate_document_module, "generate_markdown_document", fake_generate_document)


def test_phase4_quality_loop_is_opt_in() -> None:
    default_graph = build_analysis_graph()
    phase3_graph = build_analysis_graph(include_document_generation=True)
    phase4_graph = build_analysis_graph(include_quality_loop=True)

    assert "generate_documents" not in default_graph.get_graph().nodes
    assert "evaluate_documents" not in default_graph.get_graph().nodes
    assert "generate_documents" in phase3_graph.get_graph().nodes
    assert "evaluate_documents" not in phase3_graph.get_graph().nodes
    assert "generate_documents" in phase4_graph.get_graph().nodes
    assert "evaluate_documents" in phase4_graph.get_graph().nodes
    assert "prepare_quality_retry" in phase4_graph.get_graph().nodes
    assert phase4_graph.checkpointer is None


def test_phase4_evaluation_node_reuses_existing_service_without_saving() -> None:
    update = evaluate_documents(
        {
            "documents": [("Overview", "01-overview.md", "# Overview\n\n## Files\n\n`README.md`.")],
            "core_files": [_core_file()],
            "basic_files": [],
            "quality_retry_count": 0,
            "agent_steps": [],
            "tool_logs": [],
        }
    )

    assert update["result_evaluation"].textcitation_score == 1
    assert update["result_evaluation"].hallucination_risk == 0
    assert update["quality_passed"] is True
    assert update["quality_feedback"] == ""
    assert update["agent_steps"][-1].key == "evaluate_generated_documents"
    assert update["tool_logs"][-1].tool_name == "evaluate_generated_documents"


def test_phase4_quality_threshold_boundary_passes(monkeypatch) -> None:
    boundary_result = _quality_result(passed=True).model_copy(
        update={"textcitation_score": 0.7, "hallucination_risk": 0.3}
    )
    monkeypatch.setattr(
        evaluate_node_module,
        "evaluate_generated_documents",
        lambda **kwargs: boundary_result,
    )

    update = evaluate_documents(
        {
            "documents": [("Overview", "01-overview.md", "# Overview")],
            "core_files": [_core_file()],
            "basic_files": [],
        }
    )

    assert update["quality_passed"] is True


def test_phase4_retries_once_then_passes_and_preserves_all_audit(monkeypatch, tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: tmp_path)
    contexts: list[str] = []
    _install_fake_generation(monkeypatch, contexts)
    evaluations = [_quality_result(passed=False), _quality_result(passed=True)]

    def fake_evaluate(**kwargs):
        assert all(document.path == "" for document in kwargs["documents"])
        return evaluations.pop(0)

    monkeypatch.setattr(evaluate_node_module, "evaluate_generated_documents", fake_evaluate)

    result = run_analysis_graph(
        "owner/repo",
        include_quality_loop=True,
        llm_api_key="secret",
        llm_model="model",
    )

    assert len(contexts) == 14
    assert any("Quality evaluation feedback" in context for context in contexts[7:])
    assert result["quality_retry_count"] == 1
    assert result["quality_passed"] is True
    assert result["quality_feedback"] == ""
    assert len(result["llm_call_records"]) == 14
    assert [record.prompt_type for record in result["llm_call_records"]] == [
        *(prompt.title for prompt in REAL_DOCUMENT_PROMPTS),
        *(prompt.title for prompt in REAL_DOCUMENT_PROMPTS),
    ]
    generation_steps = [step.key for step in result["agent_steps"] if step.key.startswith("generate_document_")]
    assert generation_steps == [
        *(f"generate_document_{index:02d}" for index in range(1, 8)),
        *(f"generate_document_{index:02d}_retry_1" for index in range(1, 8)),
    ]
    evaluation_steps = [step.key for step in result["agent_steps"] if step.key.startswith("evaluate_generated_documents")]
    assert evaluation_steps == ["evaluate_generated_documents", "evaluate_generated_documents_retry_1"]
    retry_logs = [
        log
        for log in result["tool_logs"]
        if log.tool_name == "llm_service.generate_markdown_documents"
        and log.input.get("quality_retry_count") == 1
    ]
    assert len(retry_logs) == 7
    assert [filename for _, filename, _ in result["documents"]] == [
        prompt.filename for prompt in REAL_DOCUMENT_PROMPTS
    ]


def test_phase4_stops_after_two_retries_when_quality_stays_low(monkeypatch, tmp_path: Path) -> None:
    _create_sample_repository(tmp_path)
    monkeypatch.setattr(clone_repo_module, "clone_repository", lambda parsed_repo, temp_root: tmp_path)
    contexts: list[str] = []
    _install_fake_generation(monkeypatch, contexts)
    evaluation_calls = 0

    def always_low_quality(**kwargs):
        nonlocal evaluation_calls
        evaluation_calls += 1
        return _quality_result(passed=False)

    monkeypatch.setattr(evaluate_node_module, "evaluate_generated_documents", always_low_quality)

    result = run_analysis_graph(
        "owner/repo",
        include_quality_loop=True,
        llm_api_key="secret",
        llm_model="model",
    )

    assert len(contexts) == 21
    assert evaluation_calls == 3
    assert result["quality_retry_count"] == 2
    assert result["quality_passed"] is False
    assert "missing.py" in result["quality_feedback"]
    assert len(result["llm_call_records"]) == 21
    evaluation_steps = [step.key for step in result["agent_steps"] if step.key.startswith("evaluate_generated_documents")]
    assert evaluation_steps == [
        "evaluate_generated_documents",
        "evaluate_generated_documents_retry_1",
        "evaluate_generated_documents_retry_2",
    ]


def test_phase4_evaluation_failure_preserves_app_error_and_audit(monkeypatch) -> None:
    original_error = AppError(
        status_code=500,
        code="RESULT_EVALUATION_FAILED",
        message="evaluation failed",
        detail="invalid document",
    )

    def fail_evaluation(**kwargs):
        raise original_error

    monkeypatch.setattr(evaluate_node_module, "evaluate_generated_documents", fail_evaluation)

    with pytest.raises(AppError) as raised:
        evaluate_documents(
            {
                "documents": [("Overview", "01-overview.md", "# Overview")],
                "core_files": [_core_file()],
                "basic_files": [],
                "agent_steps": [],
                "tool_logs": [],
            }
        )

    assert raised.value is original_error
    assert raised.value.agent_steps[-1].key == "evaluate_generated_documents"
    assert raised.value.agent_steps[-1].status == "failed"
    assert raised.value.tool_logs[-1].tool_name == "evaluate_generated_documents"
    assert raised.value.tool_logs[-1].status == "failed"
