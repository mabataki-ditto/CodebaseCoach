import pytest

from app.services.file_selection_eval_service import aggregate_file_selection_reports, evaluate_file_selection

pytestmark = pytest.mark.unit


def test_evaluate_file_selection_calculates_entry_and_core_recall_at_12() -> None:
    selected_paths = [
        "README.md",
        "src/main.ts",
        "src/core/a.ts",
        *[f"src/noise-{index}.ts" for index in range(9)],
        "src/core/c.ts",
    ]
    report = evaluate_file_selection(
        selected_paths=selected_paths,
        expected_entry_paths=["src/main.ts", "src/cli.ts"],
        expected_core_paths=["src/core/a.ts", "src/core/c.ts"],
    )

    assert report["selected_files"] == selected_paths[:12]
    assert report["entry_recall"] == 0.5
    assert report["core_recall_at_12"] == 0.5
    assert report["matched_entry_files"] == ["src/main.ts"]
    assert report["missed_entry_files"] == ["src/cli.ts"]
    assert report["matched_core_files"] == ["src/core/a.ts"]
    assert report["missed_core_files"] == ["src/core/c.ts"]


def test_aggregate_file_selection_reports_uses_macro_average() -> None:
    summary = aggregate_file_selection_reports(
        [
            {"entry_recall": 1.0, "core_recall_at_12": 0.5},
            {"entry_recall": 0.5, "core_recall_at_12": 1.0},
            {"entry_recall": 0.0, "core_recall_at_12": 0.0},
        ]
    )

    assert summary == {
        "repository_count": 3,
        "average_entry_recall": 0.5,
        "average_core_recall_at_12": 0.5,
    }
