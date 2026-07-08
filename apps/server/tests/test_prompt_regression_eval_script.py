import pytest
from datetime import UTC, datetime
from pathlib import Path

from scripts.prompt_regression_eval import build_report, format_report, result_paths


pytestmark = pytest.mark.unit


def _result(
    *,
    textcitation_score: float = 1,
    coverage_score: float = 1,
    hallucination_risk: float = 0,
    usefulness_score: float = 1,
    interview_question_count: int = 8,
) -> dict:
    return {
        "documents": [{"content": "Generated document"}],
        "result_evaluation": {
            "textcitation_score": textcitation_score,
            "coverage_score": coverage_score,
            "hallucination_risk": hallucination_risk,
            "usefulness_score": usefulness_score,
            "interview_question_count": interview_question_count,
            "document_evaluations": [],
        },
    }


def test_build_report_marks_first_run_as_baseline_without_score_changes() -> None:
    report = build_report(
        baseline_result=None,
        current_result=_result(textcitation_score=0.9),
        golden={"min_textcitation_score": 0.8},
        baseline_path=Path("baseline.json"),
        current_path=Path("current.json"),
        baseline_created=True,
    )

    assert report["baseline_created"]
    assert report["golden_passed"]
    assert report["score_changes"] == []


def test_build_report_compares_scores_against_existing_baseline() -> None:
    report = build_report(
        baseline_result=_result(textcitation_score=0.9, hallucination_risk=0.1),
        current_result=_result(textcitation_score=0.7, hallucination_risk=0.2),
        golden={"min_textcitation_score": 0.8, "max_hallucination_risk": 0.15},
        baseline_path=Path("baseline.json"),
        current_path=Path("current.json"),
        baseline_created=False,
    )

    assert not report["golden_passed"]
    changes = {item["name"]: item for item in report["score_changes"]}
    assert changes["textcitation_score"]["delta"] == -0.2
    assert changes["textcitation_score"]["direction"] == "worse"
    assert changes["hallucination_risk"]["delta"] == 0.1
    assert changes["hallucination_risk"]["direction"] == "worse"


def test_format_report_includes_paths_scores_delta_and_failures() -> None:
    report = build_report(
        baseline_result=_result(textcitation_score=0.9),
        current_result=_result(textcitation_score=0.7),
        golden={"min_textcitation_score": 0.8},
        baseline_path=Path("baseline.json"),
        current_path=Path("current.json"),
        baseline_created=False,
    )

    output = format_report(report)

    assert "baseline_created: false" in output
    assert "golden_passed: false" in output
    assert "baseline_path: baseline.json" in output
    assert "current_path: current.json" in output
    assert "textcitation_score: 0.9 -> 0.7 (-0.2, worse)" in output
    assert "textcitation_score: expected at least 0.8, got 0.7" in output


def test_result_paths_use_stable_repo_slug_and_timestamp() -> None:
    baseline_path, current_path = result_paths(
        Path("data/prompt-evals"),
        "https://github.com/owner/repo.git",
        datetime(2026, 7, 5, 1, 2, 3, tzinfo=UTC),
    )

    assert baseline_path == Path("data/prompt-evals/baselines/owner_repo.json")
    assert current_path == Path("data/prompt-evals/runs/owner_repo_20260705_010203.json")