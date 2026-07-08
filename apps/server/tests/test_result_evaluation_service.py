import pytest

from app.schemas.agent import CoreFileSummary, GeneratedDocument
from app.services.result_evaluation_service import evaluate_generated_documents

pytestmark = pytest.mark.unit


def test_evaluates_references_placeholders_and_scores() -> None:
    evaluation = evaluate_generated_documents(
        core_files=[
            _core_file("README.md"),
            _core_file("src/main.ts"),
        ],
        documents=[
            GeneratedDocument(
                title="Overview",
                filename="01-overview.md",
                path="generated_docs/demo/01-overview.md",
                content="# Overview\n\n## Files\n\nUses `README.md` and `missing.ts`.\n\nTODO: fill details.",
            )
        ],
    )

    assert evaluation.document_count == 1
    assert evaluation.evaluated_document_count == 1
    assert evaluation.valid_reference_count == 1
    assert evaluation.invalid_reference_count == 1
    assert evaluation.referenced_context_file_count == 1
    assert evaluation.context_file_count == 2
    assert evaluation.textcitation_score == 0.5
    assert evaluation.coverage_score == 0.5
    assert evaluation.hallucination_risk > 0
    assert evaluation.usefulness_score < 1
    assert "TODO" in evaluation.document_evaluations[0].placeholder_hits
    assert "missing.ts" in evaluation.document_evaluations[0].invalid_referenced_file_paths


def test_counts_interview_questions_against_target() -> None:
    evaluation = evaluate_generated_documents(
        core_files=[_core_file("README.md")],
        documents=[
            GeneratedDocument(
                title="Interview",
                filename="05-interview.md",
                path="generated_docs/demo/05-interview.md",
                content="# Interview\n\n## Q1: What starts the app?\n\nUse `README.md`.\n\n## Q2: Where is entry?",
            )
        ],
    )

    assert evaluation.interview_question_count == 2
    assert evaluation.interview_question_target == 8
    assert any("Interview question count is 2" in issue for issue in evaluation.issues)


def _core_file(path: str) -> CoreFileSummary:
    return CoreFileSummary(
        path=path,
        file_type="text",
        size=10,
        content_preview="content",
        truncated=False,
        reason="test",
    )